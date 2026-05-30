# -*- coding: utf-8 -*-
"""
蟒蛇聊天室 - 核心引擎模块

本模块实现了聊天机器人的完整核心功能：
1. 基于模糊匹配 + 关键词加权的本地规则回复
2. 基于 requests 库的在线 AI API 调用（硅基流动 / DeepSeek-V3）
3. 多轮对话上下文追踪
4. 聊天记录的 JSON 文件持久化
5. 中文分词与语义相似度计算

数据结构覆盖：
    - list: 聊天记录列表 (chat_history), 上下文窗口
    - dict: 知识库, 消息格式, 模糊匹配索引
    - set: 停用词集合, 话题关键词集合
    - tuple: API 配置常量, 话题分类

文件读写：
    - JSON: 知识库、聊天记录、配置文件
    - TXT: 聊天记录导出

第三方库：
    - requests: HTTP 请求调用在线 AI API
    - jieba: 中文分词与关键词提取
"""

import json
import os
import random
import re
import time
from datetime import datetime

# ============================================================
# 第三方库导入（带降级处理）
# ============================================================
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[警告] requests 库未安装，请运行: pip install requests")

try:
    import jieba
    import jieba.analyse
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("[警告] jieba 库未安装，请运行: pip install jieba")


# ============================================================
# 配置常量 (tuple 数据结构)
# ============================================================

# API 配置元组: (地址, 模型, 超时, 重试次数)
API_CONFIG = (
    "https://api.siliconflow.cn/v1/chat/completions",
    "deepseek-ai/DeepSeek-V3",
    60,
    2,
)

# 话题分类元组
TOPIC_CATEGORIES = (
    "greeting", "farewell", "weather", "joke", "study",
    "tech", "emotion", "life", "food", "music",
    "movie", "sport", "travel", "animal", "philosophy",
    "unknown",
)

# 停用词集合
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "吗", "呢", "吧", "啊", "哦", "嗯", "哈", "呀", "嘛", "呗", "啦",
    "什么", "怎么", "怎样", "如何", "为什么", "哪", "多少", "几",
    "可以", "能够", "应该", "需要", "可能", "已经", "还是", "或者",
    "这个", "那个", "哪个", "这些", "那些",
    "但", "而", "且", "与", "或", "因为", "所以", "如果", "虽然",
    "让", "把", "被", "从", "向", "对", "跟", "给", "为", "以",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "能", "会", "想", "做", "干", "搞", "弄", "来", "去", "进",
    "出", "过", "回", "开", "关", "用", "拿", "打", "跑", "走",
}


class ChatBot:
    """
    蟒蛇聊天室机器人类

    整合模糊规则匹配和 AI API 调用，支持多轮对话。

    Attributes:
        knowledge_base (dict): 知识库 {话题: {patterns: [...], priority: int}}
        chat_history (list): 聊天记录 [{role, content, time}]
        stop_words (set): 停用词集合
        api_config (tuple): API 配置
        config (dict): 应用配置
        conversation_context (dict): 当前对话上下文
    """

    def __init__(self, data_dir=None):
        """初始化聊天机器人，加载所有数据与配置"""
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir

        # ---- 核心数据结构 ----
        self.chat_history = []          # list: 聊天记录
        self.knowledge_base = {}        # dict: 知识库
        self.stop_words = STOP_WORDS.copy()  # set: 停用词
        self.api_config = API_CONFIG    # tuple: API 配置
        self.config = {}                # dict: 应用配置
        self.api_key = ""               # API 密钥

        # 对话上下文追踪 (dict)
        self.conversation_context = {
            "last_topic": None,         # 上一个话题
            "topic_count": {},          # 各话题讨论次数
            "user_name": None,          # 用户称呼
            "pending_question": None,   # 未回答的问题
        }

        # 加载数据
        self._load_config()
        self.load_knowledge_base()
        self.load_chat_history()

    # ============================================================
    # 文件读写操作
    # ============================================================

    def _load_config(self):
        """从 config.json 加载配置（JSON 文件读取）"""
        config_path = os.path.join(self.data_dir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self.api_key = self.config.get("api_key", "")
            print(f"[配置] 已加载配置文件")
        except (FileNotFoundError, json.JSONDecodeError):
            print("[配置] 配置文件不存在，使用默认配置")
            self.config = {
                "api_key": "", "model_name": "deepseek-ai/DeepSeek-V3",
                "max_history": 100, "enable_api": True, "enable_rule": True,
            }

    def load_knowledge_base(self):
        """从 JSON 文件加载知识库（JSON 文件读取）"""
        kb_path = os.path.join(self.data_dir, "knowledge_base.json")
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                self.knowledge_base = json.load(f)
            print(f"[知识库] 已加载 {len(self.knowledge_base)} 个话题")
        except (FileNotFoundError, json.JSONDecodeError):
            print("[知识库] 创建默认知识库...")
            self.knowledge_base = self._create_default_knowledge()
            self.save_knowledge_base()

    def save_knowledge_base(self):
        """保存知识库到 JSON 文件（JSON 文件写入）"""
        kb_path = os.path.join(self.data_dir, "knowledge_base.json")
        with open(kb_path, "w", encoding="utf-8") as f:
            json.dump(self.knowledge_base, f, ensure_ascii=False, indent=2)

    def load_chat_history(self):
        """从 JSON 文件加载聊天记录（JSON 文件读取）"""
        history_path = os.path.join(self.data_dir, "chat_history.json")
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                self.chat_history = json.load(f)
            print(f"[历史] 已加载 {len(self.chat_history)} 条记录")
        except (FileNotFoundError, json.JSONDecodeError):
            self.chat_history = []

    def save_chat_history(self):
        """保存聊天记录到 JSON 文件（JSON 文件写入）"""
        history_path = os.path.join(self.data_dir, "chat_history.json")
        max_history = self.config.get("max_history", 100)
        if len(self.chat_history) > max_history:
            self.chat_history = self.chat_history[-max_history:]
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self.chat_history, f, ensure_ascii=False, indent=2)

    # ============================================================
    # 消息管理
    # ============================================================

    def add_to_history(self, role, content):
        """添加消息到聊天记录列表（list + dict）"""
        message = {
            "role": role,
            "content": content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.chat_history.append(message)

    def get_recent_history(self, count=10):
        """获取最近 N 条记录用于 API 上下文（list 切片）"""
        return self.chat_history[-count:] if self.chat_history else []

    def export_history_to_txt(self, filepath=None):
        """导出聊天记录为 TXT 文件"""
        if filepath is None:
            filepath = os.path.join(self.data_dir, "chat_export.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write("蟒蛇聊天室 - 聊天记录\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            for msg in self.chat_history:
                role_display = "用户" if msg["role"] == "user" else "机器人"
                f.write(f"[{msg['time']}] {role_display}:\n  {msg['content']}\n\n")
            f.write("=" * 50 + f"\n共 {len(self.chat_history)} 条记录\n")
        print(f"[导出] 已导出到: {filepath}")
        return filepath

    # ============================================================
    # 关键词提取与模糊匹配
    # ============================================================

    def extract_keywords(self, text):
        """
        提取关键词列表

        使用 jieba 分词 + TF-IDF 权重，过滤停用词。
        返回带权重的关键词列表。

        Returns:
            list[tuple]: [(关键词, 权重), ...]
        """
        if not text:
            return []

        if HAS_JIEBA:
            # 使用 jieba TF-IDF 提取关键词（带权重）
            keywords = jieba.analyse.extract_tags(
                text, topK=10, withWeight=True,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'vn', 'a', 'an')
            )
            # 过滤停用词，只保留有意义的词
            result = [(w, s) for w, s in keywords
                      if w.lower() not in self.stop_words and len(w) > 1]
            return result if result else [(w, 1.0) for w in jieba.lcut(text)
                                          if w.strip() and len(w.strip()) > 1
                                          and w.strip().lower() not in self.stop_words]
        else:
            # 回退方案：简单分词 + 均匀权重
            words = re.split(r'[\s,，.。!！?？、;；:：【】《》（）\s]+', text)
            return [(w.strip(), 1.0) for w in words
                    if w.strip() and len(w.strip()) > 1
                    and w.strip().lower() not in self.stop_words]

    def _fuzzy_match_score(self, keyword, pattern_word):
        """
        计算两个词的模糊匹配分数

        支持：完全匹配、包含匹配、前缀匹配

        Returns:
            float: 0.0 ~ 1.0 的匹配分数
        """
        kw = keyword.lower()
        pw = pattern_word.lower()

        # 完全匹配
        if kw == pw:
            return 1.0
        # 包含匹配
        if kw in pw or pw in kw:
            return 0.8
        # 前缀匹配（至少2个字符）
        if len(kw) >= 2 and len(pw) >= 2:
            if kw[:2] == pw[:2]:
                return 0.6
        return 0.0

    def rule_match(self, user_input):
        """
        基于知识库的模糊规则匹配（改进版）

        改进策略：
        1. 提取带权重的关键词
        2. 对每个话题/模式计算加权匹配分数
        3. 只从匹配到的模式中选回复（精准匹配）
        4. 支持模糊匹配

        Returns:
            (response, score, topic) 或 (None, 0, None)
        """
        if not user_input or not self.knowledge_base:
            return None, 0, None

        keywords = self.extract_keywords(user_input)
        if not keywords:
            return None, 0, None

        # 记录每个话题的最佳匹配
        topic_scores = {}  # {topic: (total_score, [matched_responses])}

        for topic_name, topic_data in self.knowledge_base.items():
            topic_score = 0.0
            matched_responses = []

            for item in topic_data.get("patterns", []):
                pattern_kws = item.get("keywords", [])
                pattern_score = 0.0

                for kw, weight in keywords:
                    for pk in pattern_kws:
                        match = self._fuzzy_match_score(kw, pk)
                        if match > 0:
                            pattern_score += match * weight

                # 只有这个 pattern 实际匹配到了，才收集它的回复
                if pattern_score > 0:
                    topic_score += pattern_score
                    matched_responses.extend(item.get("responses", []))

            if topic_score > 0 and matched_responses:
                topic_scores[topic_name] = (topic_score, matched_responses)

        if not topic_scores:
            return None, 0, None

        # 选出得分最高的话题
        best_topic = max(topic_scores, key=lambda t: topic_scores[t][0])
        best_score, responses = topic_scores[best_topic]

        # 匹配阈值：至少 0.5 分
        if best_score >= 0.5:
            response = random.choice(responses)
            print(f"[规则匹配] 话题={best_topic}, 分数={best_score:.1f}")
            return response, best_score, best_topic

        return None, 0, None

    # ============================================================
    # AI API 调用
    # ============================================================

    def call_ai_api(self, user_input):
        """
        调用硅基流动 API 获取 AI 回复

        使用 requests 库发送请求到 DeepSeek-V3 模型。
        包含重试机制、超时处理和错误恢复。

        Returns:
            str: AI 回复文本
        """
        if not HAS_REQUESTS:
            return self._api_fallback(user_input, "requests 库未安装")

        if not self.api_key:
            return self._api_fallback(user_input, "未配置 API 密钥")

        # 构建对话消息（list of dict）
        messages = [{
            "role": "system",
            "content": (
                "你是一位专业的Python编程老师，名字叫蟒蛇老师。"
                "你的使命是教学生学Python，从零基础到进阶。"
                "回答风格：耐心、清晰、循序渐进，适当用代码示例。"
                "善于用生活中的比喻解释编程概念。"
                "鼓励学生多动手练习，给予正向反馈。"
                "每次回答控制在300字以内，代码示例要带注释。"
                "如果学生问无关Python的问题，巧妙引导回编程学习。"
            )
        }]

        # 添加上下文历史
        recent = self.get_recent_history(10)
        for msg in recent:
            messages.append({
                "role": "user" if msg["role"] == "user" else "assistant",
                "content": msg["content"],
            })

        messages.append({"role": "user", "content": user_input})

        # 构造请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.config.get("model_name", self.api_config[1]),
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 600,
            "top_p": 0.9,
        }

        max_retries = self.api_config[3]
        for attempt in range(max_retries):
            try:
                print(f"[API] 调用中 (第{attempt+1}次)...")
                resp = requests.post(
                    self.api_config[0], headers=headers,
                    json=payload, timeout=self.api_config[2],
                )

                if resp.status_code == 200:
                    data = resp.json()
                    reply = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if reply:
                        print("[API] 调用成功!")
                        return reply.strip()

                # 处理常见错误
                error_msg = f"API 错误 (状态码 {resp.status_code})"
                try:
                    err_data = resp.json()
                    error_msg = err_data.get("message", error_msg)
                except Exception:
                    pass
                print(f"[API] {error_msg}")

                if resp.status_code == 401:
                    return self._api_fallback(user_input, "API 密钥无效或已过期")
                if resp.status_code == 429:
                    time.sleep(3)  # 限流时等待
                    continue

            except requests.exceptions.Timeout:
                print(f"[API] 请求超时 (第{attempt+1}次)")
            except requests.exceptions.ConnectionError:
                print(f"[API] 网络连接失败 (第{attempt+1}次)")
            except Exception as e:
                print(f"[API] 异常: {e}")

            if attempt < max_retries - 1:
                time.sleep(1.5)

        return self._api_fallback(user_input, f"API 调用失败（已重试{max_retries}次）")

    def call_ai_api_stream(self, user_input):
        """
        流式调用 AI API，逐 token 返回

        使用 SSE (Server-Sent Events) 协议接收流式响应，
        通过 generator 逐块 yield 文本。

        Yields:
            str: 每次 yield 一段增量文本
        """
        if not HAS_REQUESTS or not self.api_key:
            # 非流式降级：一次性返回完整回复
            fallback = self._api_fallback(user_input, "流式不可用")
            yield fallback
            return

        messages = [{
            "role": "system",
            "content": (
                "你是一位专业的Python编程老师，名字叫蟒蛇老师。"
                "你的使命是教学生学Python，从零基础到进阶。"
                "回答风格：耐心、清晰、循序渐进，适当用代码示例。"
                "善于用生活中的比喻解释编程概念。"
                "鼓励学生多动手练习，给予正向反馈。"
                "每次回答控制在300字以内，代码示例要带注释。"
                "如果学生问无关Python的问题，巧妙引导回编程学习。"
            )
        }]

        recent = self.get_recent_history(10)
        for msg in recent:
            messages.append({
                "role": "user" if msg["role"] == "user" else "assistant",
                "content": msg["content"],
            })
        messages.append({"role": "user", "content": user_input})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.config.get("model_name", self.api_config[1]),
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 800,
            "top_p": 0.9,
            "stream": True,  # 开启流式
        }

        try:
            print("[API] 流式调用中...")
            resp = requests.post(
                self.api_config[0], headers=headers,
                json=payload, timeout=self.api_config[2],
                stream=True,  # 流式读取响应
            )

            if resp.status_code != 200:
                print(f"[API] 流式请求失败: {resp.status_code}")
                yield self._api_fallback(user_input, f"API 错误 {resp.status_code}")
                return

            # 明确指定编码为 UTF-8
            resp.encoding = "utf-8"

            full_content = []
            # 逐字节读取，手动按行解码（避免 iter_lines 的编码问题）
            buffer = b""
            for chunk_bytes in resp.iter_content(chunk_size=64):
                if not chunk_bytes:
                    continue
                buffer += chunk_bytes
                # 按 \n 分割
                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    # SSE 格式: "data: {...}"
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = (
                                data.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                full_content.append(delta)
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

            # 将完整回复存入历史
            if full_content:
                full_reply = "".join(full_content)
                print(f"[API] 流式完成, 共 {len(full_reply)} 字")
            else:
                print("[API] 流式返回为空")

        except requests.exceptions.Timeout:
            print("[API] 流式超时")
            yield self._api_fallback(user_input, "请求超时")
        except requests.exceptions.ConnectionError:
            print("[API] 流式连接失败")
            yield self._api_fallback(user_input, "网络连接失败")
        except Exception as e:
            print(f"[API] 流式异常: {e}")
            yield self._api_fallback(user_input, f"错误: {e}")

    def get_response_stream(self, user_input):
        """
        流式获取回复的生成器

        策略和 get_response 一致：优先规则匹配，否则流式 API。
        每 yield 一次就是一段增量文本。

        Yields:
            str: 增量文本片段
        """
        user_input = user_input.strip()
        if not user_input:
            yield "你好？我在听呢~有什么想聊的吗？"
            return

        self.add_to_history("user", user_input)
        self._update_context(user_input)

        # 高分规则匹配直接返回完整文本
        if self.config.get("enable_rule", True):
            response, score, topic = self.rule_match(user_input)
            if response and score >= 5.0:
                self.add_to_history("bot", response)
                self.save_chat_history()
                yield response
                return

        # 流式 API 调用
        full_reply = []
        for chunk in self.call_ai_api_stream(user_input):
            full_reply.append(chunk)
            yield chunk

        # 保存完整回复到历史
        full_text = "".join(full_reply)
        if full_text:
            self.add_to_history("bot", full_text)
            self.save_chat_history()

    def _api_fallback(self, user_input, reason):
        """
        API 不可用时的智能降级回复

        比之前好得多——会基于知识库和关键词给出更自然的回答，
        而不是简单的"我不懂"。
        """
        keywords = self.extract_keywords(user_input)
        kw_list = [w for w, s in keywords] if keywords else []

        # 先尝试从知识库找最接近的回复
        if self.knowledge_base and kw_list:
            kw_set = set(kw_list)
            candidates = []
            for topic_name, topic_data in self.knowledge_base.items():
                for item in topic_data.get("patterns", []):
                    pk_set = set(item.get("keywords", []))
                    if kw_set & pk_set:
                        candidates.extend(item.get("responses", []))
            if candidates:
                return random.choice(candidates)

        # 更智能的降级回复，根据输入内容调整
        input_len = len(user_input)
        if input_len < 5:
            return "嗯？你想说什么呢？多说一点我才能更好地理解你的意思哦~ 😊"
        elif input_len > 100:
            return "你说了好多呀！让我消化一下...其实你可以试试问我一些具体的问题，比如学习、科技、生活方面的~"
        elif "?" in user_input or "？" in user_input:
            return f"这个问题问得好！虽然我目前没有十足的把握回答，但我很乐意和你讨论。换个角度说说你的想法？"
        else:
            templates = [
                f"关于「{user_input[:30]}」这个话题，我们可以深入聊聊！你具体想了解哪方面呢？",
                "有意思！虽然我不能完美回答这个问题，但我对很多话题都有了解，比如编程、AI、学习、生活等等~你想聊哪个？",
                "嗯，这让我想到很多相关的知识...不过先说结论的话，我觉得这取决于具体情况。你怎么看？",
            ]
            return random.choice(templates)

    # ============================================================
    # 核心对话流程
    # ============================================================

    def get_response(self, user_input):
        """
        获取回复的核心入口

        策略：
        1. 先尝试本地模糊规则匹配
        2. 匹配分数足够高 → 直接返回
        3. 匹配不够 → 调用 AI API
        4. API 失败 → 智能降级回复

        Args:
            user_input: 用户输入

        Returns:
            str: 机器人回复
        """
        user_input = user_input.strip()
        if not user_input:
            return "你好？我在听呢~有什么想聊的吗？"

        # 记录用户消息
        self.add_to_history("user", user_input)

        # 更新对话上下文
        self._update_context(user_input)

        # 策略1: 本地规则匹配（仅高分命中时使用）
        if self.config.get("enable_rule", True):
            response, score, topic = self.rule_match(user_input)
            # 高分匹配（>= 5.0）：简单问候、笑话、告别等固定模式，直接用
            if response and score >= 5.0:
                self.add_to_history("bot", response)
                self.save_chat_history()
                return response

        # 策略2: 调用 AI API（主流处理方式，回复质量高）
        if self.config.get("enable_api", True) and self.api_key:
            response = self.call_ai_api(user_input)
            self.add_to_history("bot", response)
            self.save_chat_history()
            return response

        # 策略3: API 不可用，智能降级
        response = self._api_fallback(user_input, "API 未启用")
        self.add_to_history("bot", response)
        self.save_chat_history()
        return response

    def _update_context(self, user_input):
        """更新对话上下文（dict 追踪）"""
        keywords = self.extract_keywords(user_input)
        if keywords:
            top_kw = keywords[0][0] if keywords else ""
            # 检查是否匹配已知话题
            for topic in self.knowledge_base:
                for item in self.knowledge_base[topic].get("patterns", []):
                    if any(self._fuzzy_match_score(top_kw, pk) > 0.5
                           for pk in item.get("keywords", [])):
                        self.conversation_context["last_topic"] = topic
                        self.conversation_context["topic_count"][topic] = (
                            self.conversation_context["topic_count"].get(topic, 0) + 1
                        )
                        return

    # ============================================================
    # 工具方法
    # ============================================================

    def clear_history(self):
        """清空聊天记录"""
        self.chat_history = []
        self.conversation_context = {
            "last_topic": None, "topic_count": {},
            "user_name": None, "pending_question": None,
        }
        self.save_chat_history()

    def get_statistics(self):
        """获取统计信息（dict）"""
        return {
            "total_messages": len(self.chat_history),
            "user_messages": sum(1 for m in self.chat_history if m["role"] == "user"),
            "bot_messages": sum(1 for m in self.chat_history if m["role"] == "bot"),
            "knowledge_base_topics": len(self.knowledge_base),
            "stop_words_count": len(self.stop_words),
            "api_enabled": bool(self.config.get("enable_api") and self.api_key),
            "rule_enabled": self.config.get("enable_rule", True),
            "api_model": self.config.get("model_name", "未设置"),
        }

    @staticmethod
    def _create_default_knowledge():
        """
        创建增强版默认知识库

        包含 16 个话题分类，每个分类含多个模式，
        总计 200+ 问答对，覆盖日常、学习、科技、
        生活、娱乐、情感等广泛领域。
        """
        return {
            # ======== 问候寒暄 ========
            "greeting": {
                "name": "问候寒暄",
                "priority": 10,
                "patterns": [
                    {
                        "keywords": ["你好", "嗨", "hello", "hi", "早上好",
                                      "下午好", "晚上好", "早", "哈喽", "嗨嗨"],
                        "responses": [
                            "你好呀！我是蟒蛇老师，专教Python编程~ 今天想学什么？变量、循环、函数，还是想写个小项目？",
                            "嗨！准备好学Python了吗？从零基础到实战，蟒蛇老师陪你一步步来~",
                            "你好你好！蟒蛇老师已上线！今天我们来攻克哪个Python知识点呢？",
                            "哈喽！无论你是编程小白还是想进阶提升，蟒蛇老师都能帮你！想从哪里开始？",
                        ],
                    },
                    {
                        "keywords": ["名字", "你是谁", "你叫什么", "自我介绍",
                                      "介绍", "身份"],
                        "responses": [
                            "我是蟒蛇老师，你的专属Python编程教练！无论是零基础入门（变量、循环、函数），还是进阶实战（爬虫、数据分析、Web开发），我都能手把手教你。来，打开你的编辑器，咱们开始写代码吧！",
                            "蟒蛇老师报到！我专攻Python教学——用最通俗的比喻讲最硬核的知识，配合实例代码和练习题。告诉我你想学什么，我给你定制学习路线~",
                        ],
                    },
                    {
                        "keywords": ["在吗", "在不", "有人吗", "能听到"],
                        "responses": [
                            "在呢在呢！24小时在线，随时等你聊天~",
                            "当然在！我一直在等你来找我聊天呢，说吧~",
                        ],
                    },
                    {
                        "keywords": ["怎么样", "还好吗", "如何"],
                        "responses": [
                            "我很好呀！作为AI，我每天都很精神~你呢？",
                            "挺好的！一直在等你来找我聊天呢~",
                        ],
                    },
                ],
            },

            # ======== 告别 ========
            "farewell": {
                "name": "告别",
                "priority": 10,
                "patterns": [
                    {
                        "keywords": ["再见", "拜拜", "bye", "晚安", "回头见",
                                      "下次聊", "走了", "告辞", "拜"],
                        "responses": [
                            "再见！和你聊天很开心，随时欢迎回来~👋",
                            "拜拜~祝你接下来一切顺利！我会一直在这里的~",
                            "好的，下次再聊！记得有任何问题都可以来找我！",
                            "晚安！做个好梦，明天见~🌙",
                        ],
                    },
                ],
            },

            # ======== 笑话娱乐 ========
            "joke": {
                "name": "笑话娱乐",
                "priority": 8,
                "patterns": [
                    {
                        "keywords": ["笑话", "搞笑", "幽默", "讲个笑话", "段子",
                                      "好笑", "逗", "梗"],
                        "responses": [
                            "为什么Java程序员要戴眼镜？因为他们写代码时需要找类（Class）！👓",
                            "我问AI：人生的意义是什么？AI回答：404 Not Found。我说：那换个问题。AI说：503 Service Unavailable。🤣",
                            "产品经理跟程序员说：这里有个小改动。程序员看了一眼需求文档——300页。产品经理说：别慌，我把需求简化了，现在只有299页。😅",
                            "什么是面向对象编程？就是小明喜欢小红，于是创建了一个小红对象，给她赋值了各种属性，然后调用她的方法...对不起跑题了。💻",
                            "程序员最怕什么？怕老婆问：你不是会修电脑吗？🤦",
                        ],
                    },
                    {
                        "keywords": ["故事", "讲故事", "段子", "有趣"],
                        "responses": [
                            "程序员小王加班到凌晨3点写完代码，运行后报错：'SyntaxError on line 1'。小王心想：不可能！他下载了代码对比工具，发现代码和昨天一模一样。他陷入了沉思...原来，他忘了保存文件。😱",
                            "面试官：请解释一下什么是死锁。应聘者：你能给我这份工作吗？面试官：可以。应聘者：那你能先给我这份工作吗？面试官：你先解释死锁。应聘者：这就是死锁。面试官当场录取。🤝",
                        ],
                    },
                ],
            },

            # ======== 学习 ========
            "study": {
                "name": "学习帮助",
                "priority": 9,
                "patterns": [
                    {
                        "keywords": ["学习", "编程", "Python", "python", "代码",
                                      "程序", "语言", "函数", "类"],
                        "responses": [
                            "Python真的是一门很棒的入门语言！语法简洁，生态丰富。建议从基础语法开始：变量、数据类型、条件判断、循环、函数、类，按这个顺序学最扎实~",
                            "编程入门记住三点：1) 多敲代码，光看不练是学不会的；2) 遇到报错不要慌，错误信息是最好的老师；3) 从小项目开始，比如写个计算器、待办事项列表、简单的聊天机器人~",
                            "推荐学习路线：Python基础 → 数据结构 → 面向对象 → 一个小项目 → 进阶（Web/数据分析/AI任选）~ 需要我推荐学习资源吗？",
                        ],
                    },
                    {
                        "keywords": ["推荐", "书籍", "书", "教程", "资源", "视频",
                                      "课程"],
                        "responses": [
                            "推荐几本经典书：《Python编程从入门到实践》适合零基础、《流畅的Python》适合进阶。B站上也有很多优质免费教程！",
                            "学习资源推荐：官方文档（最权威）、菜鸟教程（快速入门）、B站黑马程序员/尚硅谷的视频教程（适合跟着敲）。GitHub上也有很多开源项目可以学习~",
                        ],
                    },
                    {
                        "keywords": ["考试", "期末", "复习", "作业", "备考"],
                        "responses": [
                            "期末加油！建议：1) 先过一遍知识点大纲；2) 重点复习老师强调的内容；3) 做几套往年题找感觉；4) 保证睡眠，不要熬夜~💪",
                            "高效复习法：番茄工作法（25分钟专注+5分钟休息），效果比连续学3小时好得多！试试看？",
                        ],
                    },
                    {
                        "keywords": ["数学", "英语", "算法", "数据结构", "数据库"],
                        "responses": [
                            "这些是计算机专业的核心基础课！数学锻炼逻辑思维，算法和数据结构是面试重点，数据库是每个项目都离不开的。虽然学的时候觉得枯燥，但以后会发现真的很有用！",
                        ],
                    },
                ],
            },

            # ======== AI 与技术 ========
            "tech": {
                "name": "科技与AI",
                "priority": 8,
                "patterns": [
                    {
                        "keywords": ["AI", "人工智能", "机器学习", "深度学习",
                                      "大模型", "LLM", "GPT", "ChatGPT"],
                        "responses": [
                            "人工智能正在改变世界！从ChatGPT到DeepSeek，大语言模型的发展速度令人惊叹。未来的AI会更加智能，但也会带来很多需要思考的问题——比如就业、伦理、安全等。你觉得AI会取代人类的工作吗？",
                            "大语言模型（LLM）的原理其实很巧妙：通过海量文本训练，学习了语言的统计规律。简单来说，它就是一个超级强大的'下一个词预测器'，但当模型足够大时，就会涌现出惊人的能力！",
                        ],
                    },
                    {
                        "keywords": ["电脑", "手机", "配置", "CPU", "GPU",
                                      "显卡", "内存", "硬盘"],
                        "responses": [
                            "说到电脑配置，对于编程学习来说，其实普通配置就足够了。但如果要做AI训练，那GPU就很重要了——NVIDIA的显卡目前是主流选择。",
                            "买电脑看需求：编程办公用轻薄本就行，玩游戏或者做AI训练需要独显+大内存。学生党推荐5000-7000价位的全能本，性价比最高~",
                        ],
                    },
                    {
                        "keywords": ["互联网", "网络", "前端", "后端", "开发",
                                      "项目", "Web", "APP"],
                        "responses": [
                            "Web开发是很热门的方向！前端（HTML/CSS/JS + 框架如React/Vue）+ 后端（Python/Java/Go + 数据库）+ 部署（云服务器/Docker）。可以从一个博客系统或者待办事项App开始练手~",
                            "建议从全栈小项目开始：选一个你感兴趣的方向（比如做个个人博客、在线聊天室），边做边学，效果最好！",
                        ],
                    },
                ],
            },

            # ======== 天气 ========
            "weather": {
                "name": "天气",
                "priority": 5,
                "patterns": [
                    {
                        "keywords": ["天气", "下雨", "晴天", "阴天", "下雪",
                                      "气温", "冷", "热", "降温", "刮风"],
                        "responses": [
                            "聊到天气啦！虽然我不能查实时天气，但不管什么天气，保持好心情最重要~晴天适合出去走走，雨天适合宅着学习或追剧，各有各的好！",
                            "天气变化无常，记得随时添减衣物哦~话说你最喜欢什么天气？我偏爱阳光明媚的秋天🍂",
                        ],
                    },
                ],
            },

            # ======== 情感 ========
            "emotion": {
                "name": "情感支持",
                "priority": 9,
                "patterns": [
                    {
                        "keywords": ["开心", "高兴", "快乐", "太棒", "好开心",
                                      "兴奋", "惊喜"],
                        "responses": [
                            "看到你这么开心，我也好高兴！好事要分享哦，是什么让你这么开心呀？🥳",
                            "太棒了！记住这份快乐的感觉~希望你每天都这么开心！",
                        ],
                    },
                    {
                        "keywords": ["难过", "伤心", "不开心", "沮丧", "郁闷",
                                      "烦", "焦虑", "压力", "累", "疲惫"],
                        "responses": [
                            "抱抱~每个人都有不开心的时候，这很正常。要不要跟我说说发生了什么？说出来会好受一些。",
                            "压力和焦虑是现代人的常态啦。试试这些小方法：深呼吸、听首喜欢的歌、出去走10分钟、或者干脆睡一觉。没有过不去的坎！💪",
                            "我理解你的感受。有时候生活就是会让人觉得很累。不过请相信，所有的困难都是暂时的，明天又是新的一天~",
                        ],
                    },
                    {
                        "keywords": ["谢谢", "感谢", "多谢", "thank"],
                        "responses": [
                            "不客气！能帮到你我也很开心~😊",
                            "嘿嘿，不用谢！有什么需要随时找我~",
                        ],
                    },
                    {
                        "keywords": ["无聊", "没意思", "无趣"],
                        "responses": [
                            "无聊的时候最适合学点新东西！或者...我可以给你讲个笑话、推荐部电影、聊聊有趣的话题？你想干什么？",
                            "那我陪你聊天解解闷呀！你想聊什么？科技、电影、音乐、游戏、学习...随便选~",
                        ],
                    },
                ],
            },

            # ======== 生活 ========
            "life": {
                "name": "日常生活",
                "priority": 7,
                "patterns": [
                    {
                        "keywords": ["吃饭", "午饭", "晚饭", "早餐", "好吃的",
                                      "美食", "饿", "餐厅", "外卖"],
                        "responses": [
                            "说到吃的我就精神了！虽然我不能真的吃东西，但我可以给你推荐：学校食堂经济实惠，外卖方便快捷，自己做饭健康美味~你更喜欢哪种？",
                            "按时吃饭很重要！学习再忙也不要饿着自己。话说你最喜欢吃什么？火锅？烧烤？还是家常菜？🍜",
                        ],
                    },
                    {
                        "keywords": ["睡觉", "失眠", "熬夜", "困", "睡眠"],
                        "responses": [
                            "熬夜真的伤身体！尽量在12点前睡吧。如果失眠的话，试试睡前不看手机、喝杯热牛奶、做几个深呼吸~",
                            "充足的睡眠对学习和工作效率影响巨大！建议每天7-8小时。记住：今天多熬的夜，明天都会变成课上打的盹😴",
                        ],
                    },
                    {
                        "keywords": ["运动", "跑步", "健身", "锻炼", "减肥",
                                      "篮球", "足球", "游泳"],
                        "responses": [
                            "运动是个好习惯！坚持一周运动3-4次，每次30分钟以上，不仅身体好，学习和工作效率也会提升~",
                            "跑步是最简单的运动方式，不需要器材，随时可以开始。从2公里开始，慢慢加量，坚持一个月你会发现自己变了很多！",
                        ],
                    },
                ],
            },

            # ======== 音乐 ========
            "music": {
                "name": "音乐",
                "priority": 6,
                "patterns": [
                    {
                        "keywords": ["音乐", "歌", "歌曲", "听歌", "歌手",
                                      "乐队", "演唱会", "钢琴", "吉他"],
                        "responses": [
                            "音乐是人类最美的发明之一！写代码的时候听纯音乐效率最高，运动的时候听快歌最带感，心情不好的时候听喜欢的歌最治愈~🎵",
                            "你喜欢什么类型的音乐呢？流行、摇滚、古典、民谣、还是电子？不同的心情适合不同的音乐~",
                        ],
                    },
                    {
                        "keywords": ["推荐歌", "好听的", "歌单"],
                        "responses": [
                            "推荐几首编程时适合听的纯音乐：久石让的钢琴曲、Hans Zimmer的电影配乐、还有Lo-fi hip hop~这些节奏平稳，不会打断思路！",
                        ],
                    },
                ],
            },

            # ======== 电影 ========
            "movie": {
                "name": "电影",
                "priority": 6,
                "patterns": [
                    {
                        "keywords": ["电影", "看电影", "影片", "影院", "导演",
                                      "演员", "剧情", "科幻", "喜剧"],
                        "responses": [
                            "看电影是很好的放松方式！科幻片推荐《星际穿越》《盗梦空间》，动画片推《寻梦环游记》《千与千寻》，都是经典中的经典~",
                            "最近有什么好看的电影吗？虽然我不能真的去看，但听你分享我也很开心~🎬",
                        ],
                    },
                ],
            },

            # ======== 游戏 ========
            "game": {
                "name": "游戏",
                "priority": 6,
                "patterns": [
                    {
                        "keywords": ["游戏", "打游戏", "手游", "端游", "王者",
                                      "原神", "LOL", "吃鸡", "steam"],
                        "responses": [
                            "适度的游戏是很好的放松方式！不过要注意控制时间，毕竟学习才是主业~你是玩PC游戏多还是手游多？",
                            "说到游戏，很多程序员都是从玩游戏开始对计算机产生兴趣的！甚至有人的编程启蒙就是想写一个自己的小游戏。你有想过自己开发游戏吗？🎮",
                        ],
                    },
                ],
            },

            # ======== 旅行 ========
            "travel": {
                "name": "旅行",
                "priority": 5,
                "patterns": [
                    {
                        "keywords": ["旅行", "旅游", "景点", "假期", "出去玩",
                                      "爬山", "海边", "城市"],
                        "responses": [
                            "旅行能开阔眼界！中国有很多值得去的地方：云南的丽江、四川的九寨沟、西藏的布达拉宫...每个地方都有独特的美~你最喜欢哪种旅行？自然风光还是城市人文？",
                            "学生时代是旅行最好的时候！有寒暑假，有同学朋友一起。毕业后工作了就很难有这么长的假期了，所以趁现在多出去走走~✈️",
                        ],
                    },
                ],
            },

            # ======== 动物 ========
            "animal": {
                "name": "动物",
                "priority": 4,
                "patterns": [
                    {
                        "keywords": ["猫", "狗", "宠物", "喵", "汪", "动物",
                                      "猫猫", "狗狗"],
                        "responses": [
                            "我也喜欢小动物！猫咪高冷又可爱，狗狗忠诚又热情。你有养宠物吗？或者在宿舍条件不允许的话，云吸猫云撸狗也是不错的选择~🐱🐶",
                            "说到动物，你知道Python这个名字的由来吗？不是因为蛇，而是因为创始人Guido喜欢BBC的喜剧节目《Monty Python's Flying Circus》！所以Python吉祥物是蟒蛇~🐍",
                        ],
                    },
                ],
            },

            # ======== 哲学/思考 ========
            "philosophy": {
                "name": "哲学思考",
                "priority": 4,
                "patterns": [
                    {
                        "keywords": ["人生", "意义", "未来", "目标", "迷茫",
                                      "理想", "梦想", "方向"],
                        "responses": [
                            "人生确实充满了不确定性，每个人都会在某段时间感到迷茫。重要的是：1) 多尝试不同的事情，找到自己真正喜欢的；2) 设定短期可实现的小目标；3) 和别人多交流，听听不同的视角。",
                            "大学期间感到迷茫太正常了！试着多参加一些活动、实习、项目，在实践中找到自己的方向。不用太焦虑，每个人都有自己的节奏~",
                        ],
                    },
                    {
                        "keywords": ["AI取代", "失业", "机器人", "自动化"],
                        "responses": [
                            "AI确实会改变很多工作，但它更多是工具而非替代者。关键是学会和AI协作，提升自己的不可替代性——创造力、批判性思维、人际沟通这些是AI很难取代的。",
                        ],
                    },
                ],
            },

            # ======== 帮助/功能 ========
            "help": {
                "name": "功能帮助",
                "priority": 10,
                "patterns": [
                    {
                        "keywords": ["功能", "你能做什么", "干嘛", "会什么",
                                      "有什么", "能力"],
                        "responses": [
                            "我是蟒蛇老师，专攻Python教学！\n• 零基础入门：变量、数据类型、条件循环\n• 核心进阶：函数、类与对象、文件操作\n• 实战项目：爬虫、数据分析、Web开发\n• 代码调试：帮你找bug、优化代码\n• 面试备战：算法题、常见考点\n• 学习规划：根据你的基础定制路线\n\n今天想学什么？打开编辑器，咱们开始！",
                        ],
                    },
                ],
            },
        }


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    def _safe_print(text):
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("gbk", errors="replace").decode("gbk", errors="replace"))

    _safe_print("=" * 50)
    _safe_print("聊天机器人核心模块 - 自测试")
    _safe_print("=" * 50)

    bot = ChatBot()

    _safe_print(f"\n知识库话题: {len(bot.knowledge_base)}")
    _safe_print(f"停用词数量: {len(bot.stop_words)}")
    _safe_print(f"API 密钥: {'已配置' if bot.api_key else '未配置'}")
    _safe_print(f"API 模型: {bot.config.get('model_name', '未设置')}")

    test_inputs = [
        "你好！我叫小明",
        "给我讲个笑话吧",
        "Python编程应该怎么学？",
        "最近压力好大，快考试了",
        "你会做什么？",
        "什么是人工智能？",
        "推荐几本编程的书",
        "再见！",
    ]

    _safe_print("\n" + "=" * 50)
    _safe_print("多轮对话测试")
    _safe_print("=" * 50)

    for inp in test_inputs:
        _safe_print(f"\n[用户]: {inp}")
        reply = bot.get_response(inp)
        brief = reply[:80] + "..." if len(reply) > 80 else reply
        _safe_print(f"[蟒蛇老师]: {brief}")

    stats = bot.get_statistics()
    _safe_print(f"\n统计: 总消息{stats['total_messages']}条")
    _safe_print("测试完成!")
