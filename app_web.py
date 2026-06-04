# -*- coding: utf-8 -*-
"""
蟒蛇老师教Python - Flask Web 应用

功能: 用户登录 · 会话管理 · 流式对话 · 代码执行 · SQLite持久化

运行: python app_web.py → http://127.0.0.1:5000
"""

import json, os, sys, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, Response, redirect, url_for
from chatbot_core import ChatBot
import database as db

app = Flask(__name__)
app.config["SECRET_KEY"] = "python-teacher-2024"
bot = ChatBot()

# 当前活跃的对话上下文 {user_id: conversation_id}
active_conversations = {}


# ================================================================
# 页面路由
# ================================================================

@app.route("/")
def index():
    """首页 → 登录页"""
    return render_template("login.html")


@app.route("/chat")
def chat_page():
    """聊天页面"""
    return render_template("chat.html")


@app.route("/profile")
def profile_page():
    """用户后台页面"""
    return render_template("profile.html")


@app.route("/practice")
def practice_page():
    """编程刷题页面"""
    return render_template("practice.html")


# ================================================================
# 用户 Profile API
# ================================================================

@app.route("/api/profile", methods=["GET"])
def api_profile():
    """获取用户信息 + 统计 + 历史会话"""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "请提供user_id"}), 400
    profile = db.get_user_profile(user_id)
    if not profile:
        return jsonify({"error": "用户不存在"}), 404
    stats = db.get_user_stats(user_id)
    convs = db.get_conversations(user_id)
    return jsonify({
        "profile": profile,
        "stats": stats,
        "conversations": convs,
    })


@app.route("/api/profile/avatar", methods=["POST"])
def api_update_avatar():
    """更换头像"""
    data = request.get_json()
    user_id = data.get("user_id")
    avatar = data.get("avatar")
    if not user_id or not avatar:
        return jsonify({"error": "参数不完整"}), 400
    db.update_avatar(user_id, avatar)
    return jsonify({"status": "ok", "avatar": avatar})


# ================================================================
# 用户 API
# ================================================================

@app.route("/api/login", methods=["POST"])
def api_login():
    """登录/注册（带密码验证）"""
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or len(username) < 2:
        return jsonify({"status": "error", "error": "用户名至少2个字符"}), 400
    if not password or len(password) < 3:
        return jsonify({"status": "error", "error": "密码至少3位"}), 400

    success, user_id, is_new, error = db.login_or_register(username, password)
    if not success:
        return jsonify({"status": "error", "error": error}), 400

    return jsonify({
        "status": "ok",
        "user_id": user_id,
        "username": username,
        "is_new": is_new,
    })


# ================================================================
# 会话 API
# ================================================================

@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    """获取用户的所有会话列表"""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "请提供user_id"}), 400
    convs = db.get_conversations(user_id)
    return jsonify({"conversations": convs})


@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    """创建新会话"""
    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "请提供user_id"}), 400
    cid = db.create_conversation(user_id)
    active_conversations[user_id] = cid
    return jsonify({"status": "ok", "conversation_id": cid})


@app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
def api_delete_conversation(conv_id):
    """删除会话"""
    db.delete_conversation(conv_id)
    return jsonify({"status": "ok"})


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
def api_get_messages(conv_id):
    """获取会话的所有消息"""
    msgs = db.get_messages(conv_id)
    return jsonify({"messages": msgs})


@app.route("/api/conversations/<int:conv_id>/select", methods=["POST"])
def api_select_conversation(conv_id):
    """切换当前活跃会话"""
    data = request.get_json()
    user_id = data.get("user_id")
    if user_id:
        active_conversations[user_id] = conv_id
    return jsonify({"status": "ok"})


# ================================================================
# 聊天 API (带数据库持久化)
# ================================================================

@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """
    流式聊天 + 写入数据库
    """
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "请提供消息内容"}), 400

    user_message = data["message"].strip()
    user_id = data.get("user_id")
    conv_id = data.get("conversation_id")

    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    # 如果没有传入会话ID，自动创建
    if not conv_id and user_id:
        conv_id = active_conversations.get(user_id)
        if not conv_id:
            conv_id = db.create_conversation(user_id)
            active_conversations[user_id] = conv_id

    # 保存用户消息到数据库
    if conv_id:
        db.add_message(conv_id, "user", user_message)
        # 用第一句话更新标题
        msgs = db.get_messages(conv_id)
        user_msgs = [m for m in msgs if m["role"] == "user"]
        if len(user_msgs) == 1:
            title = user_message[:20] + ("..." if len(user_message) > 20 else "")
            db.update_conversation_title(conv_id, title)

    def generate():
        full_reply = []
        try:
            for chunk in bot.get_response_stream(user_message):
                full_reply.append(chunk)
                payload = json.dumps(
                    {"chunk": chunk, "status": "streaming", "conversation_id": conv_id},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"

            # 保存机器人回复到数据库
            full_text = "".join(full_reply)
            if conv_id and full_text:
                db.add_message(conv_id, "bot", full_text)

            yield "data: {\"chunk\": \"\", \"status\": \"done\"}\n\n"
        except Exception as e:
            import traceback; traceback.print_exc()
            yield f"data: {{\"chunk\": \"出错了: {str(e)}\", \"status\": \"error\"}}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ================================================================
# 其他 API
# ================================================================

@app.route("/api/execute", methods=["POST"])
def api_execute():
    """在线执行 Python 代码"""
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "请提供代码"}), 400
    code = data["code"]
    forbidden = ["import os", "import sys", "import shutil", "import subprocess",
                 "__import__", "exec(", "eval(", "open(", "rm ", "rmdir",
                 "os.system", "os.popen", "os.remove", "os.rmdir",
                 "shutil.rmtree", "sys.exit"]
    for f in forbidden:
        if f in code.lower():
            return jsonify({"output": "", "error": f"安全限制: 禁止使用 {f}"})
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=5,
            cwd=tempfile.gettempdir(),
        )
        output = result.stdout
        error = result.stderr
        if result.returncode != 0 and not error:
            error = f"进程退出码: {result.returncode}"
        return jsonify({"output": output, "error": error})
    except subprocess.TimeoutExpired:
        return jsonify({"output": "", "error": "执行超时(>5秒)"})
    except Exception as e:
        return jsonify({"output": "", "error": str(e)})


@app.route("/api/topics", methods=["GET"])
def api_topics():
    """学习话题列表"""
    topics = [
        {"icon": "01", "title": "Python入门", "desc": "print 基本运算", "q": "请讲解Python的print函数和基本运算，写出可运行的Hello World代码"},
        {"icon": "02", "title": "变量和数据类型", "desc": "int str float bool", "q": "请讲解Python四种基本数据类型和变量命名规则，每种给代码示例"},
        {"icon": "03", "title": "条件判断 if/else", "desc": "分支逻辑 比较运算符", "q": "请讲解if-elif-else条件判断，写出成绩等级判断的代码示例"},
        {"icon": "04", "title": "循环 for/while", "desc": "遍历 range 嵌套", "q": "请讲解for和while循环的区别，写出九九乘法表的完整代码"},
        {"icon": "05", "title": "列表 List", "desc": "增删改查 切片 排序", "q": "请讲解列表的增删改查操作，用水果清单的例子写完整可运行代码"},
        {"icon": "06", "title": "元组 Tuple", "desc": "不可变序列 解包 字典键", "q": "请讲解Python元组，重点是它与列表的区别，写出代码示例"},
        {"icon": "07", "title": "字典 Dict", "desc": "键值对 增删改查", "q": "请讲解字典的键值对操作，用学生成绩单的例子写代码，并与列表对比"},
        {"icon": "08", "title": "函数 def", "desc": "参数 返回值 递归", "q": "请讲解函数的定义、参数和返回值，写出计算成绩统计的函数代码"},
        {"icon": "09", "title": "类与对象 class", "desc": "OOP 封装 构造方法", "q": "请讲解类和对象，用Student类写代码，说明__init__和self的作用"},
        {"icon": "10", "title": "继承与派生", "desc": "super() 重写 多态", "q": "请讲解Python类的继承，用Animal/Dog/Cat例子说明方法重写和super()"},
        {"icon": "11", "title": "文件读写", "desc": "open read write with", "q": "请讲解文件读写操作，写出写入和读取文本文件的完整代码"},
        {"icon": "12", "title": "异常处理 try/except", "desc": "捕获错误 健壮性 finally", "q": "请讲解Python的try/except异常处理，写出捕获各种错误的代码示例"},
        {"icon": "13", "title": "实战：猜数字游戏", "desc": "随机数+循环+判断", "q": "请讲解猜数字游戏的实现，写出包含随机数和循环判断的完整代码"},
        {"icon": "14", "title": "实战：数据分析", "desc": "统计 排序 筛选", "q": "请讲解如何用Python做数据分析，以学生成绩统计为例写完整代码"},
        {"icon": "15", "title": "实战：成绩管理系统", "desc": "列表+字典+文件+菜单", "q": "请讲解如何写学生成绩管理系统，包含增删改查和排名功能的完整代码"},
    ]
    return jsonify({"topics": topics})


@app.route("/api/lessons", methods=["GET"])
def api_lessons():
    """返回所有教学知识点（预写内容+可运行代码）"""
    lessons = {
        "01": {
            "title": "Python入门",
            "concept": "Python 是解释型、面向对象的高级编程语言，由 Guido van Rossum 于1991年发布。语法简洁易读，用缩进代替花括号，非常适合初学者。",
            "points": [
                "安装：python.org 下载，勾选 Add to PATH",
                "print() 函数：在屏幕上输出文字",
                "注释：单行用 #，多行用三引号包裹",
                "缩进：Python 用4个空格表示代码块，不用 {}",
                "交互模式：终端输入 python 即可逐行执行代码",
            ],
            "code": "# 我的第一个Python程序\nprint('Hello World!')           # 输出一句话\nprint('你好，世界！')            # 中文也没问题\n\n# 基本运算\nprint(1 + 2)                    # 加法 → 3\nprint(10 - 3)                   # 减法 → 7\nprint(7 * 8)                    # 乘法 → 56\nprint(100 / 4)                  # 除法 → 25.0\n\n# f-string 格式化输出\nname = '小明'\nage = 18\nprint(f'{name}今年{age}岁，正在学Python！')",
            "ask": "请讲解Python的print函数和基本运算，写出可运行的代码示例，适合零基础理解"
        },
        "02": {
            "title": "变量和数据类型",
            "concept": "变量是存储数据的容器，就像贴了标签的收纳盒。Python 是动态类型语言，变量不需要声明类型，解释器会自动推断。",
            "points": [
                "int 整数：age = 18",
                "float 浮点数：price = 9.9",
                "str 字符串：name = '小明'（单双引号均可）",
                "bool 布尔值：is_ok = True 或 False",
                "type(x) 查看变量类型，变量名区分大小写",
                "命名规则：字母/数字/下划线，不能数字开头",
            ],
            "code": "# 四种基本数据类型\nage = 18                  # int 整数\nprice = 12.5              # float 浮点数\nname = '小明'             # str 字符串\nis_student = True         # bool 布尔值\n\n# 查看类型\nprint(type(age))          # <class 'int'>\nprint(type(price))        # <class 'float'>\nprint(type(name))         # <class 'str'>\nprint(type(is_student))   # <class 'bool'>\n\n# 变量运算\nnew_age = age + 1         # 19\nhalf_price = price / 2    # 6.25\nfull_name = name + '同学'  # 小明同学\nprint(f'{full_name}今年{new_age}岁，半价{half_price}元')\nprint(f'是否是学生: {is_student}')",
            "ask": "请详细讲解Python的四种基本数据类型(int/float/str/bool)和变量命名规则，每种类型给出代码示例"
        },
        "03": {
            "title": "条件判断 if/else",
            "concept": "条件判断让程序根据不同情况执行不同代码——就像岔路口：满足条件走一条路，不满足走另一条。",
            "points": [
                "if 条件: 条件为True时执行",
                "elif 条件: 上一个不满足时再判断",
                "else: 所有条件都不满足时执行",
                "比较运算符：== != > < >= <=",
                "逻辑运算符：and(且) or(或) not(非)",
            ],
            "code": "# 成绩等级判断\nscore = 85\n\nif score >= 90:\n    print(f'{score}分 → 优秀！')\nelif score >= 80:\n    print(f'{score}分 → 良好')\nelif score >= 60:\n    print(f'{score}分 → 及格')\nelse:\n    print(f'{score}分 → 需要加油！')\n\n# and/or 组合条件\nage = 20\nhas_ticket = True\nif age >= 18 and has_ticket:\n    print('年龄达标且有票，可以入场')\n\nif age < 18 or not has_ticket:\n    print('未成年或无票，不能入场')",
            "ask": "请讲解Python的if-elif-else条件判断和比较运算符，给出成绩等级判断的完整代码示例"
        },
        "04": {
            "title": "循环 for/while",
            "concept": "循环让计算机自动重复执行任务。for 适合已知次数，while 适合未知次数。注意避免死循环——别忘了更新条件！",
            "points": [
                "for x in 序列: 遍历每个元素",
                "range(n) 生成 0 到 n-1",
                "while 条件: 条件为True时一直循环",
                "break 跳出循环 / continue 跳过本次",
                "循环中可以嵌套循环（比如九九乘法表）",
            ],
            "code": "# for循环：遍历\nprint('=== for循环 ===')\nfor i in range(5):\n    print(f'当前是第{i+1}次循环')\n\n# 遍历列表\nfruits = ['苹果', '香蕉', '橘子', '草莓']\nprint('\\n水果清单:')\nfor fruit in fruits:\n    print(f'  我喜欢吃{fruit}')\n\n# while循环\nprint('\\n=== while循环 ===')\ncount = 1\nwhile count <= 5:\n    print(f'计数: {count}')\n    count += 1  # 必须更新，否则死循环！\n\n# 九九乘法表（嵌套循环）\nprint('\\n=== 九九乘法表 ===')\nfor i in range(1, 10):\n    for j in range(1, i+1):\n        print(f'{j}x{i}={i*j}', end='\\t')\n    print()",
            "ask": "请讲解Python的for循环和while循环的区别，并写出九九乘法表的完整代码"
        },
        "05": {
            "title": "列表 List",
            "concept": "列表是Python最常用的数据结构——有序容器，可存任意类型，支持增删改查。索引从0开始，负数索引从末尾倒数。",
            "points": [
                "创建：fruits = ['苹果', '香蕉']",
                "访问：fruits[0]→第一个，fruits[-1]→最后一个",
                "切片：fruits[1:3] 取第2到第3个",
                "增：append()末尾加，insert()指定位置加",
                "删：remove()按值，pop()按索引",
                "常用：len()长度，sort()排序，in判断存在",
            ],
            "code": "fruits = ['苹果', '香蕉', '橘子', '草莓']\nprint('原始列表:', fruits)\n\n# 增\nfruits.append('西瓜')          # 末尾添加\nfruits.insert(1, '葡萄')       # 在索引1插入\nprint('增加后:', fruits)\n\n# 删\nfruits.remove('香蕉')          # 按值删除\npopped = fruits.pop()          # 弹出最后一个\nprint(f'弹出: {popped}, 剩余: {fruits}')\n\n# 改 + 查\nfruits[0] = '大苹果'           # 修改索引0\nprint('第一个:', fruits[0])     # 访问\nprint('总数:', len(fruits))    # 长度\nprint('有橘子吗:', '橘子' in fruits)\n\n# 遍历\nprint('\\n当前水果清单:')\nfor i, f in enumerate(fruits):\n    print(f'  {i+1}. {f}')",
            "ask": "请讲解Python列表的增删改查操作，用水果清单的例子写出完整可运行代码"
        },
        "07": {
            "title": "字典 Dict",
            "concept": "字典是键值对结构，像通讯录——通过名字(键)快速查找信息(值)。键必须唯一且不可变，值可以是任意类型。",
            "points": [
                "创建：d = {'name': '小明', 'age': 18}",
                "访问：d['name']，安全访问用 d.get('key')",
                "增/改：d['score'] = 95 直接赋值",
                "删：del d['key'] 或 d.pop('key')",
                "遍历：for k,v in d.items()",
            ],
            "code": "student = {\n    'name': '小明',\n    'age': 18,\n    '语文': 85,\n    '数学': 90\n}\n\n# 访问\nprint('姓名:', student['name'])\nprint('英语:', student.get('英语', '暂无成绩'))\n\n# 增加和修改\nstudent['英语'] = 78            # 新增\nstudent['语文'] = 88            # 修改\nprint('更新后:', student)\n\n# 遍历\nprint('\\n成绩单:')\nfor subject, score in student.items():\n    print(f'  {subject}: {score}分')\n\n# 删除\nstudent.pop('age', None)\nprint('\\n删除age后:', student)",
            "ask": "请讲解Python字典的键值对操作，用学生成绩单的例子写出完整代码，并与列表做对比"
        },
        "08": {
            "title": "函数 def",
            "concept": "函数是可重复使用的代码块——输入参数，返回结果。避免重复代码，让程序结构清晰，也方便调试和测试。",
            "points": [
                "def 函数名(参数): 定义函数",
                "参数可设默认值：def greet(name='同学')",
                "return 返回结果，不写return返回None",
                "函数内变量是局部变量，外部不可访问",
                "文档字符串：函数首行三引号写说明",
            ],
            "code": "# 带默认参数的函数\ndef greet(name, greeting='你好'):\n    return f'{greeting}，{name}！'\n\nprint(greet('小明'))              # 你好，小明！\nprint(greet('小红', '早上好'))     # 早上好，小红！\n\n# 计算函数\ndef calc_stats(scores):\n    total = sum(scores)\n    avg = total / len(scores)\n    highest = max(scores)\n    lowest = min(scores)\n    return total, avg, highest, lowest\n\nscores = [85, 90, 78, 92, 88]\ntotal, avg, high, low = calc_stats(scores)\nprint(f'\\n成绩统计: 总分{total}, 平均{avg:.1f}, 最高{high}, 最低{low}')\n\n# 递归函数\ndef factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n\nprint(f'5的阶乘 = {factorial(5)}')  # 120",
            "ask": "请讲解Python函数的定义、参数和返回值，写出计算成绩统计的完整函数代码"
        },
        "09": {
            "title": "类与对象 class",
            "concept": "类(Class)是创建对象的模板，对象(Object)是类的实例。就像「汽车设计图」和「路上跑的汽车」。三大特性：封装、继承、多态。",
            "points": [
                "class 类名: 定义类",
                "__init__(self): 构造方法，创建对象时自动调用",
                "self 代表实例本身，必须是方法的第一个参数",
                "继承：class 子类(父类) 自动获得父类方法",
                "方法就是类里面的函数",
            ],
            "code": "class Student:\n    def __init__(self, name, age):\n        self.name = name\n        self.age = age\n        self.scores = []\n\n    def add_score(self, score):\n        self.scores.append(score)\n        print(f'{self.name}添加成绩: {score}')\n\n    def report(self):\n        if not self.scores:\n            return f'{self.name}暂无成绩'\n        avg = sum(self.scores) / len(self.scores)\n        return f'{self.name}({self.age}岁) 平均分: {avg:.1f}'\n\n# 创建对象\ns1 = Student('小明', 18)\ns1.add_score(90)\ns1.add_score(85)\ns1.add_score(92)\nprint(s1.report())\n\ns2 = Student('小红', 19)\ns2.add_score(88)\nprint(s2.report())\n\n# 判断类型\nprint(f'\\ns1是Student类型: {isinstance(s1, Student)}')",
            "ask": "请讲解Python的类和对象，用Student类的例子写出完整代码，说明__init__和self的作用"
        },
        "11": {
            "title": "文件读写",
            "concept": "程序运行时的数据在内存中，关闭即消失。文件读写可把数据永久保存到硬盘。用 with 语句可自动关闭文件，防止资源泄露。",
            "points": [
                "open('文件', '模式')：r读 w写 a追加",
                "with open() as f: 自动关闭文件（推荐）",
                "f.read() 读全部，f.readline() 读一行",
                "f.write() 写内容，f.writelines() 写多行",
                "务必指定 encoding='utf-8' 处理中文",
            ],
            "code": "# 写入文件\nlines = ['第一行：Hello Python!', '第二行：蟒蛇老师教编程', '第三行：文件读写很简单']\n\nwith open('demo.txt', 'w', encoding='utf-8') as f:\n    for line in lines:\n        f.write(line + '\\n')\nprint('文件写入完成！')\n\n# 读取整个文件\nprint('\\n=== 读取全部 ===')\nwith open('demo.txt', 'r', encoding='utf-8') as f:\n    content = f.read()\n    print(content)\n\n# 逐行读取\nprint('=== 逐行读取 ===')\nwith open('demo.txt', 'r', encoding='utf-8') as f:\n    for i, line in enumerate(f, 1):\n        print(f'第{i}行: {line.strip()}')",
            "ask": "请讲解Python文件读写操作，写出写入和读取文本文件的完整代码，说明with语句的好处"
        },
        "12": {
            "title": "异常处理 try/except",
            "concept": "程序运行时难免出错——用户输入了字母而非数字、文件不存在、网络断开等等。异常处理让程序优雅地应对错误，而不是直接崩溃。try 块尝试执行，except 块捕获并处理错误。",
            "points": [
                "try: 尝试执行可能出错的代码",
                "except 错误类型: 捕获特定类型的异常",
                "except Exception as e: 捕获所有异常并获取错误信息",
                "else: try成功时执行（无异常）",
                "finally: 无论是否异常都会执行（常用于清理资源）",
                "常见异常：ValueError TypeError FileNotFoundError ZeroDivisionError",
            ],
            "code": "# 1. 基本 try/except\ntry:\n    num = int('abc')  # 转换失败！\nexcept ValueError as e:\n    print(f'转换失败: {e}')\nprint('程序继续运行...')  # 不会因为异常而崩溃\n\n# 2. 捕获多种异常\nfor value in ['10', '0', 'abc', '5']:\n    try:\n        result = 100 / int(value)\n        print(f'100 / {value} = {result}')\n    except ZeroDivisionError:\n        print(f'100 / {value} = 除以零错误！')\n    except ValueError:\n        print(f'{value} 不是数字，跳过')\n    except Exception as e:\n        print(f'未知错误: {e}')\n\n# 3. try/except/else/finally 完整结构\ndef safe_read(filename):\n    try:\n        with open(filename, 'r', encoding='utf-8') as f:\n            content = f.read()\n    except FileNotFoundError:\n        print(f'文件 {filename} 不存在')\n    else:\n        print(f'读取成功，{len(content)}个字符')\n    finally:\n        print('读取操作结束\\n')\n\nsafe_read('不存在的文件.txt')\nsafe_read('demo.txt')",
            "ask": "请讲解Python的try/except异常处理机制，写出捕获ValueError、ZeroDivisionError等常见错误的代码示例"
        },
        "13": {
            "title": "实战：猜数字游戏",
            "concept": "综合运用随机数、循环、条件判断、异常处理等知识，写一个猜数字游戏。由于在线运行不支持 input()，这里用模拟方式演示完整逻辑。",
            "points": [
                "random.randint(a,b) 生成 a~b 的随机整数",
                "while True + break 实现游戏主循环",
                "if/elif/else 判断大小并给出提示",
                "计数器记录猜测次数",
                "try/except 处理非数字输入（健壮性）",
            ],
            "code": "import random\n\nanswer = random.randint(1, 100)\nprint(f'[答案已生成: 1~100之间]')\n\n# 模拟10次猜测（替代input）\nsim_guesses = [50, 75, 25, 60, 42, 80, 30, 45, 38, 40]\n\nfor guess_count, guess in enumerate(sim_guesses, 1):\n    print(f'\\n第{guess_count}次猜: {guess}')\n    if guess < answer:\n        print('  -> 太小了，再大一点！')\n    elif guess > answer:\n        print('  -> 太大了，再小一点！')\n    else:\n        print(f'  -> 恭喜猜对！答案就是{answer}，用了{guess_count}次')\n        break\nelse:\n    print(f'\\n答案揭晓: {answer}，再接再厉！')",
            "ask": "请讲解猜数字游戏的Python实现，写出完整代码，包含随机数、循环判断和计数器"
        },
        "14": {
            "title": "实战：数据分析入门",
            "concept": "Python 在数据分析领域非常强大，pandas 处理表格数据，matplotlib 画图。这里用纯 Python 实现成绩统计，展示数据分析的核心思路。",
            "points": [
                "数据分析核心：读取 → 清洗 → 统计 → 可视化",
                "Python 内置函数即可完成基础统计分析",
                "sum/len/max/min/sorted 做描述性统计",
                "用列表推导式快速筛选数据",
                "进阶可学 pandas（处理表格）和 matplotlib（画图）",
            ],
            "code": "# 学生成绩数据分析（纯Python实现）\nstudents = [\n    {'name': '小明', '语文': 85, '数学': 90, '英语': 78},\n    {'name': '小红', '语文': 92, '数学': 88, '英语': 95},\n    {'name': '小刚', '语文': 78, '数学': 95, '英语': 80},\n    {'name': '小丽', '语文': 88, '数学': 82, '英语': 90},\n    {'name': '小华', '语文': 65, '数学': 70, '英语': 72},\n]\n\n# 每科平均分\nsubjects = ['语文', '数学', '英语']\nfor subj in subjects:\n    scores = [s[subj] for s in students]\n    avg = sum(scores) / len(scores)\n    print(f'{subj} - 平均: {avg:.1f} 最高: {max(scores)} 最低: {min(scores)}')\n\n# 每个学生的总分和排名\nprint('\\n=== 总分排名 ===')\nfor s in students:\n    s['总分'] = s['语文'] + s['数学'] + s['英语']\n\nranked = sorted(students, key=lambda s: s['总分'], reverse=True)\nfor i, s in enumerate(ranked, 1):\n    print(f'{i}. {s[\"name\"]}: {s[\"总分\"]}分 (语{s[\"语文\"]} 数{s[\"数学\"]} 英{s[\"英语\"]})')\n\n# 统计及格率\npass_count = sum(1 for s in students if s['总分'] >= 180)\nprint(f'\\n总分>=180的人数: {pass_count}/{len(students)}')",
            "ask": "请讲解如何用Python做简单的数据分析，以学生成绩统计为例，写出计算平均分、排名和筛选的完整代码"
        },
        "15": {
            "title": "实战：成绩管理系统",
            "concept": "综合运用列表、字典、函数、文件读写，打造一个简单但完整的学生成绩管理系统。这是检验Python综合能力的经典项目。",
            "points": [
                "用列表+字典存储学生（姓名+各科成绩）",
                "增删改查四个核心功能，每个功能独立函数",
                "自动计算总分/平均分/排名",
                "JSON文件持久化，下次启动可加载",
                "主菜单用while循环控制流程",
            ],
            "code": "import json\n\n# 模拟数据\nstudents = [\n    {'name': '小明', '语文': 85, '数学': 90, '英语': 78},\n    {'name': '小红', '语文': 92, '数学': 88, '英语': 95},\n    {'name': '小刚', '语文': 78, '数学': 95, '英语': 80},\n]\n\ndef add_student(name, *scores):\n    s = {'name': name, '语文': scores[0], '数学': scores[1], '英语': scores[2]}\n    s['总分'] = sum(scores)\n    s['平均'] = s['总分'] / 3\n    students.append(s)\n    print(f'已添加: {name}，总分{s[\"总分\"]}，平均{s[\"平均\"]:.1f}')\n\ndef delete_student(name):\n    global students\n    students = [s for s in students if s['name'] != name]\n    print(f'已删除: {name}，剩余{len(students)}人')\n\ndef show_ranking():\n    ranked = sorted(students, key=lambda s: s.get('总分', 0), reverse=True)\n    print('\\n=== 成绩排名 ===')\n    for i, s in enumerate(ranked, 1):\n        total = s.get('总分', sum([s['语文'],s['数学'],s['英语']]))\n        print(f'{i}. {s[\"name\"]}: {total}分')\n\ndef save_to_json():\n    with open('students.json', 'w', encoding='utf-8') as f:\n        json.dump(students, f, ensure_ascii=False, indent=2)\n    print(f'已保存{len(students)}条记录到 students.json')\n\n# 演示操作\nprint('初始化3条学生数据')\nshow_ranking()\nadd_student('小丽', 88, 82, 90)\ndelete_student('小刚')\nshow_ranking()\nsave_to_json()",
            "ask": "请讲解如何用Python写一个学生成绩管理系统，包含增删改查和排名功能，写出完整代码"
        },
        "06": {
            "title": "元组 Tuple",
            "concept": "元组和列表很像，但有一个关键区别：元组不可变。一旦创建就不能修改、添加或删除元素。适合存储不应被意外修改的数据，如坐标、RGB颜色值、配置参数等。",
            "points": [
                "创建：用圆括号 () 或直接逗号分隔，t = (1, 2, 3)",
                "单元素元组要加逗号：t = (1,) 不是 (1)",
                "不可变：不能 append/remove/修改元素",
                "支持索引、切片、遍历、解包（与列表相同）",
                "比列表更省内存、访问更快，适合只读数据",
                "元组可以作为字典的键，列表不行",
            ],
            "code": "# 创建元组\npoint = (3, 5)              # 坐标\ncolors = ('红', '绿', '蓝')  # 颜色\ndata = 1, 2, 3              # 不加括号也可以\nsingle = (42,)               # 单元素必须加逗号！\n\n# 访问和切片（与列表一样）\nprint('第一个:', point[0])   # 3\nprint('切片:', colors[1:])   # ('绿', '蓝')\n\n# 解包\nx, y = point\nprint(f'x={x}, y={y}')       # x=3, y=5\n\n# 不可变性演示\n# point[0] = 10  # 这行会报错！TypeError\n\n# 元组 vs 列表\nlst = [1, 2, 3]             # 列表 72字节\ntup = (1, 2, 3)             # 元组 56字节\nprint(f'列表占用: {lst.__sizeof__()}字节')\nprint(f'元组占用: {tup.__sizeof__()}字节')\n\n# 元组可作字典键\nscores = {('小明', '语文'): 85, ('小明', '数学'): 90}\nprint(f\"小明的数学成绩: {scores[('小明', '数学')]}\")",
            "ask": "请讲解Python元组的特性，重点是它与列表的区别（不可变性、内存、字典键），写出代码示例"
        },
        "10": {
            "title": "继承与派生",
            "concept": "继承是面向对象编程的核心特性之一。子类继承父类的所有属性和方法，还可以添加新功能或重写父类方法。就像子女继承父母的特征，又有自己的特点。",
            "points": [
                "class 子类(父类): 继承父类",
                "子类自动拥有父类所有属性和方法",
                "super().__init__() 调用父类构造方法",
                "方法重写：子类定义同名方法覆盖父类方法",
                "多态：不同子类可以对同一方法有不同的实现",
                "isinstance(obj, Class) 判断对象类型",
            ],
            "code": "# 父类：动物\nclass Animal:\n    def __init__(self, name):\n        self.name = name\n\n    def speak(self):\n        return f'{self.name}发出声音...'\n\n    def info(self):\n        return f'我是{self.name}'\n\n# 子类1：狗（继承Animal）\nclass Dog(Animal):\n    def speak(self):  # 重写父类方法\n        return f'{self.name}: 汪汪汪！'\n\n    def wag_tail(self):  # 新增方法\n        return f'{self.name}摇尾巴~'\n\n# 子类2：猫（继承Animal）\nclass Cat(Animal):\n    def speak(self):\n        return f'{self.name}: 喵喵喵~'\n\n# 子类3：导盲犬（继承Dog，多层继承）\nclass GuideDog(Dog):\n    def __init__(self, name, owner):\n        super().__init__(name)  # 调用父类构造\n        self.owner = owner\n\n    def guide(self):\n        return f'{self.name}正在为{self.owner}导盲'\n\n# 测试\ndog = Dog('旺财')\ncat = Cat('咪咪')\nguide = GuideDog('阿黄', '张大爷')\n\nprint(dog.speak())       # 旺财: 汪汪汪！\nprint(cat.speak())       # 咪咪: 喵喵喵~\nprint(dog.wag_tail())    # 旺财摇尾巴~\nprint(guide.info())      # 我是阿黄\nprint(guide.guide())     # 阿黄正在为张大爷导盲\n\n# 类型判断\nprint(f'\\ndog是Dog: {isinstance(dog, Dog)}')\nprint(f'dog是Animal: {isinstance(dog, Animal)}')\nprint(f'guide是Dog: {isinstance(guide, Dog)}')",
            "ask": "请讲解Python类的继承与派生，用Animal/Dog/Cat的例子说明方法重写、super()和多态，写出完整代码"
        },
    }
    topic_id = request.args.get("id", "")
    if topic_id and topic_id in lessons:
        return jsonify({"lesson": lessons[topic_id]})
    return jsonify({"lessons": lessons})


@app.route("/api/quiz/<chapter>", methods=["GET"])
def api_quiz(chapter):
    """获取某章自测题"""
    quizzes = {
        "01": {"title": "Python入门", "questions": [
            {"q": "Python中print('Hello')的输出结果是？", "opts": ["Hello", "Hello World", "print", "出错"], "ans": 0, "exp": "print()函数输出括号内的内容，字符串用引号包裹"},
            {"q": "Python中单行注释用什么符号？", "opts": ["//", "#", "--", "/*"], "ans": 1, "exp": "Python单行注释以#开头，//是Java/C++的注释符"},
            {"q": "下面哪个是正确的Python语句？", "opts": ["print 'Hi'", "print(Hi)", "print('Hi')", "PRINT('Hi')"], "ans": 2, "exp": "print()必须加括号，字符串必须用引号包裹"},
            {"q": "1 + 2 * 3 的结果是？", "opts": ["9", "7", "6", "10"], "ans": 1, "exp": "Python单行注释以#开头，//是Java/C++的注释符"},
            {"q": "Python文件的后缀名通常是？", "opts": [".java", ".cpp", ".py", ".txt"], "ans": 2, "exp": "print()必须加括号，字符串必须用引号包裹"},
        ], "blanks": [
            {"q": "在屏幕上输出'Hello'的Python语句是____", "ans": "print('Hello')", "exp": "print()是Python最基础的输出函数，括号内放要输出的内容"},
            {"q": "Python中做单行注释的符号是____", "ans": "#", "exp": "#是Python的单行注释符号，解释器会忽略#之后的内容"},
            {"q": "表达式 10 / 2 的结果是____（填数字）", "ans": "5.0", "exp": "10/2=5.0，Python中除法结果总是浮点数"},
            {"q": "Python文件的后缀名是____（不含点号）", "ans": "py", "exp": "Python源文件的后缀名是py，例如hello.py"},
            {"q": "字符串拼接'abc'+'def'的结果是____", "ans": "abcdef", "exp": "字符串用+拼接，'abc'+'def'结果是'abcdef'"},
        ]},
        "02": {"title": "变量和数据类型", "questions": [
            {"q": "下面哪个是合法的变量名？", "opts": ["2name", "my_name", "class", "my-name"], "ans": 1, "exp": "3.14是浮点数，type()返回<class 'float'>"},
            {"q": "type(3.14)的结果是？", "opts": ["int", "float", "str", "bool"], "ans": 1, "exp": "3.14是浮点数，type()返回<class 'float'>"},
            {"q": "name = '小明'，name是什么类型？", "opts": ["int", "float", "str", "list"], "ans": 2, "exp": "用引号包裹的内容是字符串str类型"},
            {"q": "True 和 False 属于什么类型？", "opts": ["int", "str", "bool", "NoneType"], "ans": 2, "exp": "用引号包裹的内容是字符串str类型"},
            {"q": "x = 5; x = 'hello'; print(type(x))输出？", "opts": ["<class 'int'>", "<class 'str'>", "<class 'float'>", "报错"], "ans": 1, "exp": "==用于比较是否相等，=用于赋值"},
        ], "blanks": [{"q": "Python中存储整数的数据类型叫", "ans": "int", "exp": "int即integer(整数)，Python中用int类型存储整数"}, {"q": "存储小数的数据类型叫", "ans": "float", "exp": "float是浮点数类型，用于存储小数"}, {"q": "存储文本的数据类型叫", "ans": "str", "exp": "str即string(字符串)，用引号包裹的文本都是str类型"}, {"q": "存储真假值的数据类型叫", "ans": "bool", "exp": "bool即boolean(布尔)，只有True和False两个值"}, {"q": "查看变量类型的函数是", "ans": "type", "exp": "type()函数可以查看任何变量或值的数据类型"}]},
        "03": {"title": "条件判断", "questions": [
            {"q": "if x > 5: 中，冒号的作用是？", "opts": ["结束语句", "开始代码块", "装饰", "无意义"], "ans": 1, "exp": "==用于比较是否相等，=用于赋值"},
            {"q": "以下哪个是Python的比较运算符？", "opts": ["=", "==", "=>", "< >"], "ans": 1, "exp": "range(3)生成0,1,2，循环体执行3次"},
            {"q": "if score >= 60 表示？", "opts": ["大于60", "小于60", "大于等于60", "不等于60"], "ans": 2, "exp": ">=表示大于或等于"},
            {"q": "and 运算符表示什么逻辑？", "opts": ["或者", "并且", "否定", "异或"], "ans": 1, "exp": "append()方法在列表末尾添加元素"},
            {"q": "以下代码输出？\nx=10\nif x>5:\n    print('A')\nelse:\n    print('B')", "opts": ["A", "B", "AB", "无输出"], "ans": 0, "exp": "变量名不能以数字开头，不能包含连字符，不能是关键字class"},
        ], "blanks": [{"q": "判断相等使用的运算符是", "ans": "==", "exp": "一个=是赋值，两个==才是判断相等"}, {"q": "条件判断的关键字是", "ans": "if", "exp": "if是条件判断的起始关键字"}, {"q": "'并且'对应的逻辑运算符是", "ans": "and", "exp": "and翻译为'并且'，两边条件都为True结果才为True"}, {"q": "'或者'对应的逻辑运算符是", "ans": "or", "exp": "or翻译为'或者'，两边条件任一个为True结果就为True"}, {"q": "不满足if时继续判断用哪个关键字", "ans": "elif", "exp": "elif是else if的缩写，用于不满足if时继续判断另一个条件"}]},
        "04": {"title": "循环", "questions": [
            {"q": "range(5)生成哪些数字？", "opts": ["1~5", "0~4", "0~5", "1~4"], "ans": 1, "exp": "range(3)生成0,1,2，循环体执行3次"},
            {"q": "for i in range(3): 循环执行几次？", "opts": ["2", "3", "4", "0"], "ans": 1, "exp": "元组创建后不能修改、添加或删除元素——这叫'不可变'"},
            {"q": "while True: 是什么循环？", "opts": ["有限循环", "无限循环", "不循环", "错误"], "ans": 1, "exp": "d['a']是用键'a'直接访问，键不存在会报错"},
            {"q": "break 语句的作用是？", "opts": ["跳过本次", "跳出循环", "继续循环", "程序暂停"], "ans": 1, "exp": "add(2,3)返回2+3=5"},
            {"q": "以下代码输出？\nfor i in range(2):\n    print(i,end='')", "opts": ["12", "01", "012", "0"], "ans": 1, "exp": "__init__是构造方法，创建对象时自动调用，用于初始化属性"},
        ], "blanks": [{"q": "生成0到4数字序列的代码是range(____)", "ans": "5", "exp": "range(5)生成0,1,2,3,4共5个数字"}, {"q": "跳出循环的关键字是", "ans": "break", "exp": "break用于立即终止循环，跳出循环体"}, {"q": "跳过本次循环继续下一次的关键字是", "ans": "continue", "exp": "continue跳过本次循环的剩余代码，进入下一次循环"}, {"q": "for循环中用来遍历的东西叫____对象", "ans": "可迭代", "exp": "for循环可以遍历列表、字符串、range等'可迭代'对象"}, {"q": "while循环中必须有的防止死循环的语句叫____条件", "ans": "更新", "exp": "while循环必须更新条件变量，否则会变成死循环"}]},
        "05": {"title": "列表", "questions": [
            {"q": "fruits = ['苹果','香蕉']，fruits[0]的值是？", "opts": ["香蕉", "苹果", "None", "报错"], "ans": 1, "exp": "append()方法在列表末尾添加元素"},
            {"q": "fruits.append('橘子')的作用是？", "opts": ["删除橘子", "末尾加橘子", "开头加橘子", "排序"], "ans": 1, "exp": "super().__init__()调用父类的构造方法，避免重复写初始化代码"},
            {"q": "len([1,2,3])的结果是？", "opts": ["2", "3", "4", "报错"], "ans": 1, "exp": "with语句会自动调用close()关闭文件，即使发生异常也能正确关闭"},
            {"q": "fruits.pop()的作用是？", "opts": ["添加元素", "弹出最后一个", "弹出第一个", "排序"], "ans": 1, "exp": "除数为零会触发ZeroDivisionError"},
            {"q": "以下代码输出？\nnums=[1,2,3]\nnums[0]=99\nprint(nums)", "opts": ["[1,2,3]", "[99,2,3]", "[99,1,2,3]", "报错"], "ans": 1, "exp": "import语句导入模块，让程序可以使用模块中的函数"},
        ], "blanks": [{"q": "获取列表长度的函数是", "ans": "len", "exp": "len()是Python内置函数，返回序列的长度"}, {"q": "列表末尾添加元素的方法叫", "ans": "append", "exp": "append()是列表的方法，将元素添加到末尾"}, {"q": "fruits[0]访问的是第____个元素（填数字）", "ans": "1", "exp": "列表索引从0开始，fruits[0]是第1个元素，-1是最后一个"}, {"q": "删除列表末尾元素的方法是", "ans": "pop", "exp": "pop()默认删除并返回列表最后一个元素"}, {"q": "判断元素是否在列表中用什么关键字", "ans": "in", "exp": "in关键字判断元素是否存在于列表(或其他序列)中"}]},
        "06": {"title": "元组", "questions": [
            {"q": "元组使用什么符号定义？", "opts": ["[]", "{}", "()", "<>"], "ans": 2, "exp": "while True条件永远为True，是无限循环"},
            {"q": "元组和列表最大的区别是？", "opts": ["元组更快", "元组不可变", "元组更小", "元组可排序"], "ans": 1, "exp": "元组创建后不能修改、添加或删除元素——这叫'不可变'"},
            {"q": "t = (1,2,3); t[0]=9 会怎样？", "opts": ["修改成功", "报错TypeError", "元组变为[9,2,3]", "创建新元组"], "ans": 1, "exp": "len([1,2,3,4])返回列表元素个数4"},
            {"q": "单个元素的元组怎么写？", "opts": ["(1)", "(1,)", "[1]", "{1}"], "ans": 1, "exp": "global声明后才能在函数内部修改全局变量的值"},
            {"q": "a,b = (1,2) 这句叫做？", "opts": ["打包", "解包", "赋值", "索引"], "ans": 1},
        ], "blanks": [{"q": "定义元组使用的括号是____括号", "ans": "圆", "exp": "元组使用圆括号，与数学中的括号一致"}, {"q": "单元素元组必须加什么符号", "ans": "逗号", "exp": "单元素元组(1,)必须有逗号，否则(1)会被当作数字1"}, {"q": "元组最核心的特性是____（两个字）", "ans": "不可变", "exp": "元组一旦创建就不能修改——不可变(immutable)是其最核心特征"}, {"q": "元组可以同时给多个变量赋值，这叫____", "ans": "解包", "exp": "a,b=(1,2)将元组拆开分别赋值，这叫解包或拆包"}, {"q": "元组可以作为字典的____（两个字）", "ans": "键", "exp": "元组不可变所以可哈希，因此可以作为字典的键"}]},
        "07": {"title": "字典", "questions": [
            {"q": "字典由什么组成？", "opts": ["索引和值", "键和值", "数字和字符串", "列表和元组"], "ans": 1, "exp": "d['a']是用键'a'直接访问，键不存在会报错"},
            {"q": "d={'a':1}; d['a']结果是？", "opts": ["a", "1", "None", "报错"], "ans": 1},
            {"q": "d.get('x','默认')的作用是？", "opts": ["设置x", "安全获取x，没有返回默认", "删除x", "创建x"], "ans": 1},
            {"q": "del d['key']的作用是？", "opts": ["添加键", "修改键", "删除键值对", "获取值"], "ans": 2, "exp": "len()函数返回列表的元素个数"},
            {"q": "字典和列表的共同点是？", "opts": ["都用[]", "都可变", "都有序(3.7+)", "都不可变"], "ans": 1},
        ], "blanks": [{"q": "Python字典由____和值组成（两个字）", "ans": "键", "exp": "字典是键值对(key-value pair)结构"}, {"q": "安全获取字典值的方法叫", "ans": "get", "exp": "get()方法安全获取值，键不存在返回默认值而不是报错"}, {"q": "删除字典键值对的关键字是", "ans": "del", "exp": "del关键字可以删除变量、列表元素、字典键值对等"}, {"q": "遍历字典键值对的方法是____（英文）", "ans": "items", "exp": "dict.items()返回(键,值)元组的可迭代对象，用于遍历"}, {"q": "d={'a':1} 中'a'被称为什么", "ans": "键", "exp": "字典中的'a'是键(key)，1是对应的值(value)"}]},
        "08": {"title": "函数", "questions": [
            {"q": "定义函数的关键字是？", "opts": ["function", "def", "func", "define"], "ans": 1, "exp": "add(2,3)返回2+3=5"},
            {"q": "def add(a,b): return a+b，add(2,3)结果是？", "opts": ["5", "23", "None", "报错"], "ans": 0, "exp": "Python定义函数用def关键字（define的缩写）", "exp": "字典由键(key)和值(value)组成，通过键来访问对应的值", "exp": "元组使用圆括号()定义，区别于列表的[]和字典的{}", "exp": "列表索引从0开始，fruits[0]是第一个元素'苹果'", "exp": "range(5)生成0,1,2,3,4共5个数", "exp": "冒号表示接下来是缩进的代码块"},
            {"q": "return 语句的作用是？", "opts": ["打印输出", "返回结果", "结束循环", "定义变量"], "ans": 1},
            {"q": "def f(x=10): 中的10是什么？", "opts": ["必须参数", "默认参数", "关键字参数", "返回值"], "ans": 1},
            {"q": "函数内部定义的变量是？", "opts": ["全局变量", "局部变量", "类变量", "常量"], "ans": 1},
        ], "blanks": [{"q": "定义函数的关键字是____（英文）", "ans": "def", "exp": "def是define的缩写，Python用def定义函数"}, {"q": "函数返回结果的关键字是", "ans": "return", "exp": "return将计算结果返回给调用处"}, {"q": "函数的第一参数如果是实例本身，通常命名为", "ans": "self", "exp": "类中方法的第一个参数是self，代表实例本身"}, {"q": "函数内部定义的变量叫做____变量", "ans": "局部", "exp": "函数内定义的变量只能在函数内访问，称为局部变量"}, {"q": "给参数设定备选值的参数叫____参数", "ans": "默认", "exp": "def f(x=10)中10是默认值，有默认值的参数叫默认参数"}]},
        "09": {"title": "类与对象", "questions": [
            {"q": "定义类的关键字是？", "opts": ["object", "def", "class", "self"], "ans": 2, "exp": "元组不支持修改元素，尝试修改会抛出TypeError"},
            {"q": "__init__方法在什么时候调用？", "opts": ["手动调用", "创建对象时自动", "删除对象时", "修改属性时"], "ans": 1, "exp": "__init__是构造方法，创建对象时自动调用，用于初始化属性"},
            {"q": "self 代表什么？", "opts": ["类本身", "实例本身", "父类", "全局变量"], "ans": 1},
            {"q": "s = Student()，s是什么？", "opts": ["类", "对象/实例", "方法", "属性"], "ans": 1},
            {"q": "类里面的函数叫什么？", "opts": ["属性", "方法", "参数", "构造器"], "ans": 1},
        ], "blanks": [{"q": "定义类的关键字是____（英文）", "ans": "class", "exp": "class关键字用于定义类，类是创建对象的模板"}, {"q": "创建对象时自动调用的方法是____（英文）", "ans": "__init__", "exp": "__init__是构造方法(前后各两个下划线)，创建对象时自动调用"}, {"q": "代表实例本身的关键字是____（英文）", "ans": "self", "exp": "self是约定俗成的名称，代表实例对象本身"}, {"q": "类里面定义的函数叫____（两个字）", "ans": "方法", "exp": "类中定义的函数叫方法(method)，第一个参数必须是self"}, {"q": "通过类创建出来的具体东西叫____（两个字）", "ans": "对象", "exp": "类是模板，对象是根据模板创建的具体实例"}]},
        "10": {"title": "继承与派生", "questions": [
            {"q": "class Dog(Animal): 表示？", "opts": ["Dog包含Animal", "Dog继承Animal", "Animal继承Dog", "两者无关"], "ans": 1, "exp": "super().__init__()调用父类的构造方法，避免重复写初始化代码"},
            {"q": "super().__init__()的作用？", "opts": ["创建新对象", "调用父类构造方法", "重写方法", "删除对象"], "ans": 1},
            {"q": "子类重写父类方法称为？", "opts": ["重载", "重写/覆盖", "继承", "封装"], "ans": 1},
            {"q": "isinstance(dog, Animal)返回？", "opts": ["False", "True", "None", "报错"], "ans": 1},
            {"q": "子类可以新增父类没有的方法吗？", "opts": ["不可以", "可以", "只有父类同意才行", "需要特殊语法"], "ans": 1},
        ], "blanks": [{"q": "子类继承父类的关键字是class 子类(____)", "ans": "父类", "exp": "class Dog(Animal)括号中写的是父类名Animal"}, {"q": "调用父类方法使用的函数是____（英文）", "ans": "super", "exp": "super()函数用于调用父类的方法"}, {"q": "子类重新定义父类已有方法叫____（两个字）", "ans": "重写", "exp": "子类重新定义父类已有方法，称为重写或覆盖(override)"}, {"q": "判断对象类型的函数是____（英文）", "ans": "isinstance", "exp": "isinstance()检查对象是否属于某个类或其子类"}, {"q": "同一方法在不同子类有不同表现叫____（两个字）", "ans": "多态", "exp": "不同子类对同一方法有不同实现，这叫多态(polymorphism)"}]},
        "11": {"title": "文件读写", "questions": [
            {"q": "open('f.txt','w')的'w'表示？", "opts": ["读取", "写入", "追加", "二进制"], "ans": 1, "exp": "with语句会自动调用close()关闭文件，即使发生异常也能正确关闭"},
            {"q": "with open() as f: 的好处是？", "opts": ["更快", "自动关闭文件", "支持中文", "加密"], "ans": 1},
            {"q": "f.read()的作用是？", "opts": ["读一行", "读全部", "写一行", "关闭文件"], "ans": 1},
            {"q": "处理中文文件应指定？", "opts": ["encoding='gbk'", "encoding='utf-8'", "encoding='ascii'", "不需要"], "ans": 1},
            {"q": "'a'模式打开文件做什么？", "opts": ["读取", "覆盖写入", "末尾追加", "删除"], "ans": 2, "exp": "d.get('x','默认')是安全访问，键不存在返回默认值而不是报错"},
        ], "blanks": [{"q": "打开文件的函数是____（英文）", "ans": "open", "exp": "open()是Python的内置函数，用于打开文件"}, {"q": "以写入模式打开文件的模式参数是", "ans": "w", "exp": "'w'即write模式，打开文件用于写入(会覆盖已有内容)"}, {"q": "以读取模式打开文件的模式参数是", "ans": "r", "exp": "'r'即read模式，打开文件用于读取"}, {"q": "自动管理文件上下文的语句是____（英文）", "ans": "with", "exp": "with语句自动管理资源，退出代码块时自动关闭文件"}, {"q": "处理中文文件必须指定的参数是____（英文）", "ans": "encoding", "exp": "处理中文文件必须指定encoding='utf-8'，否则可能乱码"}]},
        "12": {"title": "异常处理", "questions": [
            {"q": "捕获异常的关键字是？", "opts": ["catch", "except", "error", "throw"], "ans": 1, "exp": "除数为零会触发ZeroDivisionError"},
            {"q": "5/0 会抛出什么异常？", "opts": ["ValueError", "TypeError", "ZeroDivisionError", "KeyError"], "ans": 2, "exp": "finally块中的代码无论是否发生异常都会执行，常用于释放资源", "exp": "return将计算结果返回给调用者"},
            {"q": "finally块中的代码何时执行？", "opts": ["只有在出错时", "只有不出错时", "无论如何都执行", "从来不执行"], "ans": 2, "exp": "self代表当前实例对象本身，通过self访问实例的属性和方法"},
            {"q": "int('abc')会抛出什么异常？", "opts": ["TypeError", "ValueError", "KeyError", "IndexError"], "ans": 1},
            {"q": "except Exception as e: 中的e是什么？", "opts": ["错误码", "异常对象", "错误行号", "文件名"], "ans": 1},
        ], "blanks": [{"q": "捕获异常的关键字是____（英文）", "ans": "except", "exp": "except用于捕获并处理try块中抛出的异常"}, {"q": "尝试执行可能出错代码的关键字是____（英文）", "ans": "try", "exp": "try块包含可能出错的代码"}, {"q": "无论是否异常都会执行的块叫____（英文）", "ans": "finally", "exp": "finally块中的代码无论如何都会执行(即使有异常或return)"}, {"q": "除数为零会抛出的异常类型叫____（英文）", "ans": "ZeroDivisionError", "exp": "除数为零触发ZeroDivisionError(零除错误)"}, {"q": "int('abc')会抛出的异常叫____（英文）", "ans": "ValueError", "exp": "int()无法转换非数字字符串时抛出ValueError(值错误)"}]},
        "13": {"title": "猜数字游戏", "questions": [
            {"q": "random.randint(1,100)生成什么？", "opts": ["1~99", "1~100", "0~100", "0~99"], "ans": 1, "exp": "import语句导入模块，让程序可以使用模块中的函数"},
            {"q": "import random 的作用？", "opts": ["安装random", "导入random模块", "定义random函数", "删除random"], "ans": 1},
            {"q": "while True 如何停止？", "opts": ["自动停止", "用break跳出", "用continue", "无法停止"], "ans": 1},
            {"q": "int(input())把输入转为什么？", "opts": ["字符串", "浮点数", "整数", "布尔值"], "ans": 2, "exp": "使用break可以跳出while True这样的无限循环", "exp": "子类定义与父类同名方法，会覆盖父类的方法，这叫重写(override)"},
            {"q": "游戏中的guess_count变量作用？", "opts": ["存答案", "记录猜测次数", "存数字", "没用"], "ans": 1},
        ], "blanks": [{"q": "生成随机整数的函数是random.____（英文）", "ans": "randint", "exp": "random.randint(a,b)返回a到b之间(含两端)的随机整数"}, {"q": "导入随机数模块的语句是import ____（英文）", "ans": "random", "exp": "import random导入标准库中的random模块"}, {"q": "把用户输入转为整数用____函数", "ans": "int", "exp": "int()将字符串转为整数，input()返回的总是字符串"}, {"q": "游戏循环中，猜对后跳出循环用____关键字", "ans": "break", "exp": "break跳出循环，游戏猜对后不再继续循环"}, {"q": "import random中的random叫做____（两个字）", "ans": "模块", "exp": "Python中每个.py文件就是一个模块(module)"}]},
        "14": {"title": "数据分析", "questions": [
            {"q": "sum([1,2,3])的结果？", "opts": ["5", "6", "4", "报错"], "ans": 1, "exp": "len([1,2,3,4])返回列表元素个数4"},
            {"q": "len([1,2,3,4])的结果？", "opts": ["3", "4", "5", "报错"], "ans": 1},
            {"q": "sorted([3,1,2])的结果？", "opts": ["[3,1,2]", "[1,2,3]", "[1,3,2]", "报错"], "ans": 1},
            {"q": "max([10,20,5])的结果？", "opts": ["10", "5", "20", "35"], "ans": 2, "exp": "sorted()返回排序后的新列表，默认升序", "exp": "f.read()一次性读取文件的全部内容"},
            {"q": "[x for x in range(3)]是什么？", "opts": ["元组", "列表推导式", "字典", "集合"], "ans": 1},
        ], "blanks": [{"q": "求列表总和的函数是____（英文）", "ans": "sum", "exp": "sum()对可迭代对象求和"}, {"q": "求列表最大值的函数是____（英文）", "ans": "max", "exp": "max()返回最大值"}, {"q": "对列表排序的函数是____（英文）", "ans": "sorted", "exp": "sorted()返回排序后的新列表，原列表不变"}, {"q": "求列表长度的函数是____（英文）", "ans": "len", "exp": "len()返回序列长度/元素个数"}, {"q": "快速生成新列表的语法叫列表____式", "ans": "推导", "exp": "列表推导式用[x for x in seq]语法快速生成新列表"}]},
        "15": {"title": "成绩管理系统", "questions": [
            {"q": "json.dump()的作用？", "opts": ["读取JSON", "写入JSON", "删除JSON", "打印JSON"], "ans": 1, "exp": "global声明后才能在函数内部修改全局变量的值"},
            {"q": "global关键字的作用？", "opts": ["定义常量", "在函数内修改全局变量", "导入模块", "定义类"], "ans": 1},
            {"q": "lambda s: s['score']是什么？", "opts": ["函数定义", "匿名函数/lambda", "类定义", "变量赋值"], "ans": 1},
            {"q": "sorted(data, reverse=True)表示？", "opts": ["升序", "降序", "随机", "不排序"], "ans": 1},
            {"q": "字典中存多个学生用什么结构？", "opts": ["单个字典", "列表嵌套字典", "元组", "集合"], "ans": 1},
        ], "blanks": [{"q": "数据写入JSON文件用json.____（英文）", "ans": "dump", "exp": "json.dump()将Python对象写入文件，dump有'倾倒/写入'的意思"}, {"q": "在函数内修改全局变量需要____声明", "ans": "global", "exp": "在函数内修改全局变量必须先声明global"}, {"q": "排序时reverse=True表示____序排列", "ans": "降", "exp": "reverse=True是降序(从大到小)，reverse=False或不写是升序"}, {"q": "用lambda定义的函数叫____函数", "ans": "匿名", "exp": "lambda创建的是匿名函数，没有def和函数名"}, {"q": "JSON文件中存储结构化数据，类似于Python的____类型", "ans": "字典", "exp": "JSON格式与Python字典高度相似，都是键值对结构"}]},
    }

    if chapter in quizzes:
        return jsonify({"quiz": quizzes[chapter]})
    return jsonify({"error": "章节不存在"}), 404


@app.route("/api/quiz/submit", methods=["POST"])
def api_quiz_submit():
    """提交自测答案"""
    data = request.get_json()
    user_id = data.get("user_id")
    chapter = data.get("chapter")
    answers = data.get("answers", [])
    blank_answers = data.get("blankAnswers", [])

    if not user_id or not chapter:
        return jsonify({"error": "参数不完整"}), 400

    # 获取正确答案
    quizzes_resp = api_quiz(chapter)
    quiz_data = quizzes_resp[0].get("quiz") if isinstance(quizzes_resp, tuple) else quizzes_resp.get_json().get("quiz")
    if not quiz_data:
        return jsonify({"error": "章节不存在"}), 404

    # 选择题评分
    questions = quiz_data["questions"]
    mcq_correct = sum(1 for i, q in enumerate(questions)
                      if i < len(answers) and answers[i] == q["ans"])

    # 填空题评分（忽略大小写和空格差异）
    blanks = quiz_data.get("blanks", [])
    blank_correct = sum(1 for i, b in enumerate(blanks)
                        if i < len(blank_answers)
                        and blank_answers[i].strip().lower() == b["ans"].strip().lower())

    total = len(questions) + len(blanks)
    correct = mcq_correct + blank_correct

    # 每题详细结果
    mcq_results = []
    for i, q in enumerate(questions):
        user_ans = answers[i] if i < len(answers) else -1
        is_correct = user_ans == q["ans"]
        mcq_results.append({
            "q": q["q"],
            "user": q["opts"][user_ans] if 0 <= user_ans < len(q["opts"]) else "未作答",
            "correct_ans": q["opts"][q["ans"]],
            "ok": is_correct,
            "exp": q.get("exp", f'正确答案是「{q["opts"][q["ans"]]}」')
        })

    blank_results = []
    for i, b in enumerate(blanks):
        user_ans = blank_answers[i].strip() if i < len(blank_answers) else ""
        is_correct = user_ans.lower() == b["ans"].strip().lower()
        blank_results.append({
            "q": b["q"].replace("____", "______"),
            "user": user_ans or "未作答",
            "correct_ans": b["ans"],
            "ok": is_correct,
            "exp": b.get("exp", f'正确答案是「{b["ans"]}」')
        })

    # 只保留最高分
    best = db.save_quiz_score(user_id, chapter, correct, total)

    return jsonify({
        "score": correct,
        "total": total,
        "mcq_score": mcq_correct, "mcq_total": len(questions),
        "blank_score": blank_correct, "blank_total": len(blanks),
        "mcq_results": mcq_results,
        "blank_results": blank_results,
        "best": best,
        "is_new_best": correct >= best,
        "title": quiz_data["title"],
    })


@app.route("/api/quiz/scores", methods=["GET"])
def api_quiz_scores():
    """获取用户所有自测成绩"""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "请提供user_id"}), 400
    scores = db.get_quiz_scores(user_id)
    return jsonify({"scores": scores})


# ================================================================
# 编程刷题
# ================================================================

PROBLEMS = [
    {
        "id": 1, "title": "两数之和", "difficulty": "简单",
        "desc": "给定一个整数列表nums和一个目标值target，找出列表中和为target的两个数的索引。假设只有一组解。",
        "template": "def two_sum(nums, target):\n    # 在此编写代码\n    pass\n\n# 测试\nnums = [2, 7, 11, 15]\ntarget = 9\nprint(two_sum(nums, target))",
        "test_cases": [
            {"input": "", "expected": "[0, 1]", "desc": "nums=[2,7,11,15],target=9", "test": "print(two_sum([2,7,11,15], 9))"},
            {"input": "", "expected": "[1, 2]", "desc": "nums=[3,2,4],target=6", "test": "print(two_sum([3,2,4], 6))"},
            {"input": "", "expected": "[0, 1]", "desc": "nums=[3,3],target=6", "test": "print(two_sum([3,3], 6))"},
        ],
        "hint": "提示: 可以用字典存储遍历过的数字，实现O(n)时间复杂度"
    },
    {
        "id": 2, "title": "判断回文数", "difficulty": "简单",
        "desc": "判断一个整数是否是回文数。回文数指正序和倒序读都一样的数字。负数不是回文数。",
        "template": "def is_palindrome(x):\n    # 在此编写代码\n    pass\n\n# 测试\nprint(is_palindrome(121))\nprint(is_palindrome(-121))\nprint(is_palindrome(10))",
        "test_cases": [
            {"input": "", "expected": "True", "desc": "回文:121", "test": "print(is_palindrome(121))"},
            {"input": "", "expected": "False", "desc": "回文:-121", "test": "print(is_palindrome(-121))"},
            {"input": "", "expected": "False", "desc": "回文:10", "test": "print(is_palindrome(10))"},
        ],
        "hint": "提示: 可以转成字符串比较，也可以用数学方法反转数字"
    },
    {
        "id": 3, "title": "爬楼梯", "difficulty": "简单",
        "desc": "假设你正在爬楼梯，需要n阶才能到达楼顶。每次可以爬1或2个台阶，问有多少种不同的方法爬到楼顶？n为正整数。",
        "template": "def climb_stairs(n):\n    # 返回不同爬法数量\n    pass\n\n# 测试\nprint(climb_stairs(5))",
        "test_cases": [
            {"input": "", "expected": "2", "desc": "爬2阶", "test": "print(climb_stairs(2))"},
            {"input": "", "expected": "3", "desc": "爬3阶", "test": "print(climb_stairs(3))"},
            {"input": "", "expected": "8", "desc": "爬5阶", "test": "print(climb_stairs(5))"},
        ],
        "hint": "提示: 本质是斐波那契数列 f(n)=f(n-1)+f(n-2)，用循环而非递归避免超时"
    },
    {
        "id": 4, "title": "反转字符串", "difficulty": "简单",
        "desc": "编写一个函数，将输入的字符串反转并返回。不要使用切片[::-1]，自己实现反转逻辑。",
        "template": "def reverse_string(s):\n    # 返回反转后的字符串\n    pass\n\n# 测试\nprint(reverse_string('hello'))",
        "test_cases": [
            {"input": "", "expected": "olleh", "desc": "反转hello", "test": "print(reverse_string('hello'))"},
            {"input": "", "expected": "nohtyP", "desc": "反转Python", "test": "print(reverse_string('Python'))"},
            {"input": "", "expected": "", "desc": "反转空串", "test": "print(reverse_string(''))"},
        ],
        "hint": "提示: 用循环从后往前遍历，或使用双指针交换字符"
    },
    {
        "id": 5, "title": "斐波那契数列", "difficulty": "中等",
        "desc": "输出斐波那契数列的前N项。斐波那契数列：F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2)。用列表形式返回前N项。",
        "template": "def fibonacci(n):\n    # 返回斐波那契数列前n项(列表)\n    pass\n\n# 测试\nprint(fibonacci(10))",
        "test_cases": [
            {"input": "", "expected": "[0, 1, 1, 2, 3]", "desc": "斐波那契前5项", "test": "print(fibonacci(5))"},
            {"input": "", "expected": "[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]", "desc": "斐波那契前10项", "test": "print(fibonacci(10))"},
            {"input": "", "expected": "[0]", "desc": "斐波那契前1项", "test": "print(fibonacci(1))"},
        ],
        "hint": "提示: 用循环比递归更高效，注意n=1的特殊情况"
    },
    {
        "id": 6, "title": "统计字符频率", "difficulty": "中等",
        "desc": "给定一个字符串，统计每个字符出现的次数，返回一个字典。只统计字母和数字，忽略大小写差异。",
        "template": "def char_count(s):\n    # 返回字典 {字符: 出现次数}\n    pass\n\n# 测试\nprint(char_count('Hello World! 123'))",
        "test_cases": [
            {"input": "", "expected": "{'a': 2, 'b': 2, 'c': 2}", "desc": "统计:abcABC", "test": "print(char_count('abcABC'))"},
            {"input": "", "expected": "{'h': 1, 'e': 1, 'l': 2, 'o': 1, '1': 1, '2': 1, '3': 1}", "desc": "统计:Hello 123!", "test": "print(char_count('Hello 123!'))"},
            {"input": "", "expected": "{}", "desc": "统计:空字符串", "test": "print(char_count(''))"},
        ],
        "hint": "提示: 用s.isalnum()判断是否为字母或数字"
    },
    {
        "id": 7, "title": "找出缺失数字", "difficulty": "中等",
        "desc": "给定一个包含0到n中n个不重复数字的列表，找出缺失的那个数字。例如输入[3,0,1]返回2，输入[0,1]返回2。",
        "template": "def missing_number(nums):\n    # 返回缺失的数字\n    pass\n\n# 测试\nprint(missing_number([3,0,1]))",
        "test_cases": [
            {"input": "", "expected": "2", "desc": "缺失:3,0,1", "test": "print(missing_number([3,0,1]))"},
            {"input": "", "expected": "2", "desc": "缺失:0,1", "test": "print(missing_number([0,1]))"},
            {"input": "", "expected": "8", "desc": "缺失:0-9少8", "test": "print(missing_number([9,6,4,2,3,5,7,0,1]))"},
        ],
        "hint": "提示: 数学法——0到n的和减去列表元素和即得缺失数；或使用异或运算"
    },
    {
        "id": 8, "title": "有效括号判断", "difficulty": "中等",
        "desc": "给定一个只包含 ()、[]、{} 的字符串，判断括号是否有效配对。有效条件：左括号必须用同类型右括号闭合，且闭合顺序正确。",
        "template": "def is_valid(s):\n    # 返回 True 或 False\n    pass\n\n# 测试\nprint(is_valid('()[]{}'))",
        "test_cases": [
            {"input": "", "expected": "True", "desc": "括号:()[]{}", "test": "print(is_valid('()[]{}'))"},
            {"input": "", "expected": "False", "desc": "括号:([)]", "test": "print(is_valid('([)]'))"},
            {"input": "", "expected": "True", "desc": "括号:{[]}", "test": "print(is_valid('{[]}'))"},
        ],
        "hint": "提示: 使用栈(列表模拟)，遇到左括号入栈，右括号检查栈顶是否匹配"
    },
    {
        "id": 9, "title": "最大子数组和", "difficulty": "困难",
        "desc": "给定一个整数列表，找出具有最大和的连续子数组，返回其最大和。",
        "template": "def max_subarray(nums):\n    # 返回最大子数组和\n    pass\n\n# 测试\nprint(max_subarray([-2,1,-3,4,-1,2,1,-5,4]))",
        "test_cases": [
            {"input": "", "expected": "6", "desc": "子数组和典型", "test": "print(max_subarray([-2,1,-3,4,-1,2,1,-5,4]))"},
            {"input": "", "expected": "1", "desc": "子数组和单元素", "test": "print(max_subarray([1]))"},
            {"input": "", "expected": "23", "desc": "子数组和全正", "test": "print(max_subarray([5,4,-1,7,8]))"},
        ],
        "hint": "提示: 使用Kadane算法(动态规划)，dp[i]=max(nums[i], dp[i-1]+nums[i])"
    },
    {
        "id": 10, "title": "合并有序列表", "difficulty": "困难",
        "desc": "给定两个已按升序排列的整数列表，将它们合并为一个新的升序列表并返回。不要使用sort()，利用两个列表已有序的特性。",
        "template": "def merge_sorted(a, b):\n    # 返回合并后的升序列表\n    pass\n\n# 测试\nprint(merge_sorted([1,3,5], [2,4,6]))",
        "test_cases": [
            {"input": "", "expected": "[1, 2, 3, 4, 5, 6]", "desc": "合并两个等长", "test": "print(merge_sorted([1,3,5], [2,4,6]))"},
            {"input": "", "expected": "[1, 2, 3]", "desc": "合并一个空", "test": "print(merge_sorted([1,2,3], []))"},
            {"input": "", "expected": "[1, 1, 1, 2, 3, 4]", "desc": "合并含重复", "test": "print(merge_sorted([1,1,3], [1,2,4]))"},
        ],
        "hint": "提示: 双指针法——用两个指针分别遍历两个列表，每次取较小的元素"
    },
]


@app.route("/api/problems", methods=["GET"])
def api_problems():
    """获取编程题列表"""
    return jsonify({"problems": [{
        "id": p["id"], "title": p["title"],
        "difficulty": p["difficulty"], "desc": p["desc"], "hint": p["hint"]
    } for p in PROBLEMS]})


@app.route("/api/problems/<int:pid>", methods=["GET"])
def api_problem_detail(pid):
    """获取某道题详情+模板"""
    for p in PROBLEMS:
        if p["id"] == pid:
            return jsonify({"problem": p})
    return jsonify({"error": "题目不存在"}), 404


@app.route("/api/problems/<int:pid>/submit", methods=["POST"])
def api_problem_submit(pid):
    """提交代码评测"""
    data = request.get_json()
    code = data.get("code", "")
    if not code.strip():
        return jsonify({"error": "代码不能为空"}), 400

    # 检查是否有危险的import
    if "import os" in code or "import sys" in code or "open(" in code:
        return jsonify({"error": "代码包含禁止的操作"}), 400

    for p in PROBLEMS:
        if p["id"] != pid:
            continue

        results = []
        passed = 0
        for tc in p["test_cases"]:
            try:
                # 用测试用例输入替换代码中所有的 print() 调用
                # 将代码中的 print(function_call) 替换为 print(function_call(test_input))
                # 简单策略: 在代码末尾追加测试调用
                test_code = code + "\n" + tc.get("test", "")
                r = subprocess.run(
                    [sys.executable, "-c", test_code],
                    capture_output=True, text=True,
                    timeout=5, cwd=tempfile.gettempdir(),
                )
                actual = r.stdout.strip()
                expected = tc["expected"]
                ok = actual == expected or actual.replace(" ", "") == expected.replace(" ", "")
                if ok:
                    passed += 1
                results.append({
                    "input": tc.get("desc", tc["input"])[:80],
                    "expected": expected,
                    "actual": actual[:100] if actual else "(无输出)",
                    "ok": ok,
                    "error": r.stderr.strip()[:100] if r.stderr else "",
                })
            except subprocess.TimeoutExpired:
                results.append({"input": tc.get("desc","")[:60], "expected": tc["expected"],
                                "actual": "超时(>5秒)", "ok": False, "error": "代码执行超时"})
            except Exception as e:
                results.append({"input": tc.get("desc","")[:60], "expected": tc["expected"],
                                "actual": str(e)[:100], "ok": False, "error": str(e)})

        total = len(p["test_cases"])
        return jsonify({
            "passed": passed, "total": total,
            "results": results,
            "all_pass": passed == total,
        })

    return jsonify({"error": "题目不存在"}), 404


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(bot.get_statistics())


# ================================================================
# 禁用缓存
# ================================================================
@app.after_request
def add_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "页面未找到"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "服务器内部错误"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("蟒蛇老师教Python - Web 应用")
    print("=" * 50)
    print(f"知识库: {len(bot.knowledge_base)} 话题 | SQLite数据库已就绪")
    print("访问: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
