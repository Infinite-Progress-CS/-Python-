# 🤖 蟒蛇老师教Python

一个基于 Python 开发的智能聊天对话机器人。

## 项目简介

本项目实现了一个完整的 AI 智能聊天对话机器人系统，支持三种交互方式：
- **命令行 (CLI)**：终端文本对话
- **Web 应用 (Flask)**：浏览器端聊天界面
- **桌面应用 (Tkinter)**：图形化桌面聊天程序

## 项目结构

```
├── chatbot_core.py          # 核心引擎（规则匹配 + AI API + 数据管理）
├── knowledge_base.json      # 知识库（自动生成，预设多话题问答）
├── chat_history.json        # 聊天记录存储
├── config.json              # 配置文件（API密钥、模型设置等）
├── app_cli.py               # 命令行入口
├── app_web.py               # Flask Web 应用入口
├── app_gui.py               # Tkinter 桌面应用入口
├── templates/
│   └── chat.html            # Web 聊天页面（HTML + JS）
├── static/
│   └── style.css            # Web 页面样式
└── README.md                # 项目说明文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install flask requests jieba
```

### 2. 运行应用

**命令行版本：**
```bash
python app_cli.py
```

**Web 应用版本：**
```bash
python app_web.py
# 浏览器访问: http://127.0.0.1:5000
```

**桌面 GUI 版本：**
```bash
python app_gui.py
```

## 需求覆盖

| 课程要求 | 实现方式 |
|---------|---------|
| 输入→处理→输出闭环 | 用户输入 → 规则匹配/API调用 → 返回回复 |
| 3种以上数据结构 | `list`（聊天记录）、`dict`（知识库/消息）、`set`（停用词）、`tuple`（配置常量） |
| 文件读写操作 | JSON（知识库/聊天记录/配置）+ TXT（导出记录） |
| 编码规范 | 函数/类含 docstring，关键代码含注释，PEP8 规范 |
| 技术扩展 | ✅ Flask Web 应用 + ✅ Tkinter GUI 应用 |
| 第三方库 | `requests`（API调用）、`jieba`（中文分词）、`flask`（Web框架） |

## 功能特点

- 🧠 双重回复策略：本地规则匹配 + 在线 AI API 调用
- 💬 多话题支持：问候、笑话、学习、技术问答、情感支持等
- 📝 聊天记录持久化：自动保存、支持导出 TXT
- 🌐 Web 界面：响应式设计，支持 PC 和移动端
- 🖥️ 桌面 GUI：原生 Tkinter 界面，操作流畅
