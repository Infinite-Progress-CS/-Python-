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
        {"icon": "01", "title": "Python入门", "desc": "print Hello World", "q": "Python应该怎么安装？写第一个Hello World"},
        {"icon": "02", "title": "变量和数据类型", "desc": "int str float bool", "q": "什么是变量？Python有哪些数据类型？"},
        {"icon": "03", "title": "条件判断 if/else", "desc": "分支逻辑 比较运算符", "q": "if elif else怎么用？举个简单的例子"},
        {"icon": "04", "title": "循环 for/while", "desc": "遍历 range 嵌套循环", "q": "for循环和while循环有什么区别？"},
        {"icon": "05", "title": "列表 List", "desc": "增删改查 切片 排序", "q": "列表有哪些常用操作？给我一些代码示例"},
        {"icon": "06", "title": "字典 Dict", "desc": "键值对 增删改查", "q": "字典和列表有什么区别？什么时候用字典？"},
        {"icon": "07", "title": "函数 def", "desc": "参数 返回值 作用域", "q": "什么是函数？怎么定义和调用函数？"},
        {"icon": "08", "title": "类与对象 class", "desc": "OOP 继承 多态", "q": "什么是面向对象编程？类和对象怎么理解？"},
        {"icon": "09", "title": "文件读写", "desc": "open read write with", "q": "Python怎么读写文件？with语句有什么好处？"},
        {"icon": "10", "title": "实战：猜数字游戏", "desc": "循环+条件判断综合", "q": "带我写一个猜数字小游戏"},
        {"icon": "11", "title": "实战：数据分析", "desc": "pandas matplotlib", "q": "用Python做数据分析怎么入门？"},
        {"icon": "12", "title": "实战：成绩管理系统", "desc": "列表+字典+文件+菜单", "q": "带我写一个学生成绩管理系统"},
    ]
    return jsonify({"topics": topics})


@app.route("/api/lessons", methods=["GET"])
def api_lessons():
    """返回所有教学知识点（预写内容+代码）"""
    lessons = {
        "01": {
            "title": "Python入门",
            "concept": "Python 是一门解释型、面向对象的高级编程语言，由 Guido van Rossum 于1991年发布。语法简洁易读，非常适合编程初学者。",
            "points": [
                "安装 Python：官网 python.org 下载安装包，勾选「Add to PATH」",
                "第一个程序：print('Hello World') 在屏幕上输出文字",
                "注释：用 # 写单行注释，用三引号写多行注释",
                "缩进：Python 用缩进（4个空格）代替 {} 表示代码块",
            ],
            "code": "# 第一个Python程序\nprint('Hello World!')  # 输出一句话\n\n# 变量和计算\nname = input('你叫什么名字？')\nprint(f'你好，{name}！欢迎学Python')",
            "ask": "Python应该怎么安装？写第一个Hello World程序"
        },
        "02": {
            "title": "变量和数据类型",
            "concept": "变量是存储数据的容器，就像贴了标签的收纳盒。Python 是动态类型语言，变量不需要声明类型，解释器会自动推断。",
            "points": [
                "整数 int：age = 18",
                "浮点数 float：price = 9.9",
                "字符串 str：name = '小明'（单引号或双引号均可）",
                "布尔值 bool：is_student = True / False",
                "type() 函数可以查看变量的数据类型",
            ],
            "code": "# 四种基本数据类型\nage = 18                # int 整数\nprice = 9.9             # float 浮点数\nname = '小明'           # str 字符串\nis_student = True       # bool 布尔值\n\nprint(type(age))        # <class 'int'>\nprint(type(name))       # <class 'str'>\nprint(f'{name}今年{age}岁')  # f-string格式化",
            "ask": "什么是变量？Python有哪些数据类型？请举代码例子"
        },
        "03": {
            "title": "条件判断 if/else",
            "concept": "条件判断让程序根据不同情况执行不同代码，就像人生的岔路口——不同的选择通向不同的结果。",
            "points": [
                "if 条件: 当条件为True时执行",
                "elif 条件: 上一个条件不满足时，再判断这个条件",
                "else: 以上条件都不满足时执行",
                "比较运算符：== != > < >= <=",
                "逻辑运算符：and or not",
            ],
            "code": "score = 85\n\nif score >= 90:\n    print('优秀！')\nelif score >= 80:\n    print('良好')\nelif score >= 60:\n    print('及格')\nelse:\n    print('需要加油！')\n\n# 结合逻辑运算符\nage = 20\nhas_ticket = True\nif age >= 18 and has_ticket:\n    print('可以入场')",
            "ask": "if elif else怎么用？举个简单例子，带代码"
        },
        "04": {
            "title": "循环 for/while",
            "concept": "循环让计算机重复执行任务——就像你做20个俯卧撑，计算机可以一瞬间完成。for循环用于已知次数，while循环用于未知次数。",
            "points": [
                "for 变量 in 序列: 遍历列表、字符串、range()等",
                "range(n) 生成 0 到 n-1 的数字序列",
                "while 条件: 条件为True时一直循环",
                "break 跳出循环，continue 跳过本次循环",
            ],
            "code": "# for循环：已知次数\nfor i in range(5):\n    print(f'第{i+1}次：Hello!')\n\n# 遍历列表\nfruits = ['苹果', '香蕉', '橘子']\nfor fruit in fruits:\n    print(f'我喜欢吃{fruit}')\n\n# while循环：未知次数\ncount = 0\nwhile count < 3:\n    print(f'计数: {count}')\n    count += 1  # 别忘了加1，否则死循环！",
            "ask": "for循环和while循环有什么区别？请举代码例子"
        },
        "05": {
            "title": "列表 List",
            "concept": "列表是Python中最常用的数据结构之一，像一个有序的容器，可以存放任意类型的数据，支持增删改查操作。",
            "points": [
                "创建：fruits = ['苹果', '香蕉', '橘子']",
                "访问：fruits[0] 获取第一个（索引从0开始）",
                "切片：fruits[1:3] 获取第2到第3个",
                "添加：append() 末尾追加，insert() 指定位置插入",
                "删除：remove() 按值删除，pop() 按索引删除",
                "常用：len() 长度，sort() 排序，in 判断是否存在",
            ],
            "code": "fruits = ['苹果', '香蕉', '橘子']\n\n# 增\nfruits.append('草莓')       # 末尾添加\nfruits.insert(1, '葡萄')    # 位置1插入\n\n# 删\nfruits.remove('香蕉')       # 按值删除\nlast = fruits.pop()         # 弹出最后一个\n\n# 改\nfruits[0] = '大苹果'        # 索引0改为大苹果\n\n# 查\nprint(fruits[0])            # 大苹果\nprint(len(fruits))          # 列表长度\nprint('橘子' in fruits)     # 判断是否存在",
            "ask": "列表有哪些常用操作？给我一些代码示例"
        },
        "06": {
            "title": "字典 Dict",
            "concept": "字典是键值对（key-value）结构，像现实中的通讯录——通过名字（键）查找电话（值），查找速度极快。",
            "points": [
                "创建：student = {'name': '小明', 'age': 18}",
                "访问：student['name'] 通过键获取值",
                "添加/修改：student['score'] = 95",
                "删除：del student['age'] 或 pop('age')",
                "遍历：for key, value in student.items()",
                "安全访问：student.get('grade', '未设置')",
            ],
            "code": "student = {\n    'name': '小明',\n    'age': 18,\n    'scores': [85, 90, 78]\n}\n\n# 访问\nprint(student['name'])        # 小明\nprint(student.get('grade', '暂无'))  # 安全访问\n\n# 增改\nstudent['grade'] = '大二'     # 新增键值对\nstudent['age'] = 19           # 修改已有值\n\n# 遍历\nfor key, value in student.items():\n    print(f'{key}: {value}')\n\n# 删除\ndel student['scores']",
            "ask": "字典和列表有什么区别？什么时候用字典？"
        },
        "07": {
            "title": "函数 def",
            "concept": "函数是一段可重复使用的代码块，像一个黑盒子——输入参数，输出返回值。使用函数可以避免重复代码，让程序更清晰。",
            "points": [
                "定义：def 函数名(参数): 代码块",
                "参数：位置参数、默认参数、关键字参数",
                "返回值：return 语句返回结果",
                "作用域：函数内部变量是局部的，外部变量是全局的",
                "文档字符串：函数第一行用三引号写说明",
            ],
            "code": "def greet(name, greeting='你好'):\n    '''向用户打招呼的函数'''\n    return f'{greeting}，{name}！'\n\n# 调用\nprint(greet('小明'))              # 你好，小明！\nprint(greet('小红', '早上好'))     # 早上好，小红！\n\n# 计算面积的函数\ndef calculate_area(width, height):\n    area = width * height\n    return area\n\nresult = calculate_area(5, 3)\nprint(f'面积是: {result}')        # 面积是: 15",
            "ask": "什么是函数？怎么定义和调用函数？请举代码例子"
        },
        "08": {
            "title": "类与对象 class",
            "concept": "类（Class）是创建对象的模板，对象（Object）是类的实例。就像「汽车设计图」和「路上跑的汽车」的关系。面向对象编程三大特性：封装、继承、多态。",
            "points": [
                "class 类名: 定义类",
                "__init__(self): 构造函数，创建对象时自动调用",
                "self: 代表实例本身，必须是第一个参数",
                "继承：class 子类(父类) 继承父类的属性和方法",
                "方法：类里面的函数叫方法",
            ],
            "code": "class Student:\n    '''学生类'''\n    def __init__(self, name, age):\n        self.name = name\n        self.age = age\n        self.scores = []\n\n    def add_score(self, score):\n        '''添加成绩'''\n        self.scores.append(score)\n\n    def average(self):\n        '''计算平均分'''\n        if not self.scores:\n            return 0\n        return sum(self.scores) / len(self.scores)\n\n# 创建对象\ns1 = Student('小明', 18)\ns1.add_score(90)\ns1.add_score(85)\nprint(f'{s1.name}的平均分: {s1.average()}')",
            "ask": "什么是面向对象编程？类和对象怎么理解？请举代码例子"
        },
        "09": {
            "title": "文件读写",
            "concept": "程序运行时的数据在内存中，关闭就没了。文件读写可以把数据永久保存到硬盘上，下次运行时再读出来。",
            "points": [
                "open('文件', '模式'): r读 w写 a追加",
                "with open() as f: 自动关闭文件（推荐）",
                "f.read() 读取全部，f.readline() 读取一行",
                "f.write() 写入内容",
                "编码：指定 encoding='utf-8' 处理中文",
            ],
            "code": "# 写入文件\nwith open('test.txt', 'w', encoding='utf-8') as f:\n    f.write('第一行：Hello Python!\\n')\n    f.write('第二行：你好世界！\\n')\n\n# 读取文件\nwith open('test.txt', 'r', encoding='utf-8') as f:\n    content = f.read()\n    print(content)\n\n# 逐行读取\nwith open('test.txt', 'r', encoding='utf-8') as f:\n    for line in f:\n        print(line.strip())",
            "ask": "Python怎么读写文件？with语句有什么好处？"
        },
        "10": {
            "title": "实战：猜数字游戏",
            "concept": "综合运用变量、循环、条件判断、输入输出、随机数等知识，写一个完整的命令行小游戏。这是检验Python基础的最佳练习！",
            "points": [
                "import random 导入随机数模块",
                "random.randint(1, 100) 生成1-100的随机数",
                "while True 无限循环 + break 跳出",
                "int(input()) 获取用户输入并转整数",
                "计数器：每猜一次 +1，最后显示用了多少次",
            ],
            "code": "import random\n\nanswer = random.randint(1, 100)\nguess_count = 0\n\nprint('=== 猜数字游戏 ===')\nprint('我想了一个1-100的数字，来猜猜看！')\n\nwhile True:\n    guess = int(input('你猜的数字是: '))\n    guess_count += 1\n\n    if guess < answer:\n        print('太小了！再大一点~')\n    elif guess > answer:\n        print('太大了！再小一点~')\n    else:\n        print(f'恭喜！你用了{guess_count}次猜对了！')\n        break",
            "ask": "带我写一个猜数字小游戏，要完整的代码"
        },
        "11": {
            "title": "实战：数据分析",
            "concept": "Python 在数据分析领域应用广泛。pandas 是最核心的数据处理库，matplotlib 用于画图可视化。处理表格数据就像操作 Excel，但更强大。",
            "points": [
                "pip install pandas matplotlib 安装库",
                "pd.read_csv() 读取CSV文件",
                "df.head() 查看前几行，df.describe() 统计摘要",
                "df['列名'] 选取列，df.groupby() 分组统计",
                "plt.plot() 折线图，plt.bar() 柱状图",
            ],
            "code": "import pandas as pd\nimport matplotlib.pyplot as plt\n\n# 创建示例数据\ndata = {\n    '姓名': ['小明', '小红', '小刚', '小丽'],\n    '语文': [85, 92, 78, 88],\n    '数学': [90, 88, 95, 82],\n    '英语': [78, 95, 80, 90]\n}\ndf = pd.DataFrame(data)\n\n# 数据分析\nprint(df.describe())        # 统计摘要\nprint(df['语文'].mean())    # 语文平均分\n\n# 画图\ndf.set_index('姓名')[['语文','数学','英语']].plot(kind='bar')\nplt.title('学生成绩对比')\nplt.show()",
            "ask": "用Python做数据分析怎么入门？pandas怎么用？"
        },
        "12": {
            "title": "实战：学生成绩管理系统",
            "concept": "综合运用列表、字典、函数、文件读写等知识，打造一个完整的学生成绩管理系统。这是检验Python综合能力的经典项目，也是期末大作业的常见题型。",
            "points": [
                "用列表+字典存储学生数据（学号、姓名、成绩）",
                "实现增删改查（CRUD）四个核心功能",
                "计算总分、平均分、排名",
                "用文件读写持久化数据（JSON或CSV格式）",
                "命令行菜单交互，while循环控制主流程",
            ],
            "code": "import json\n\nstudents = []  # 存储所有学生\n\ndef add_student():\n    '''添加学生'''\n    name = input('姓名: ')\n    score = float(input('成绩: '))\n    students.append({'name': name, 'score': score})\n    print(f'已添加: {name}')\n\ndef show_all():\n    '''显示所有学生，按成绩排名'''\n    sorted_list = sorted(students, key=lambda s: s['score'], reverse=True)\n    print('\\n=== 成绩排名 ===')\n    for i, s in enumerate(sorted_list, 1):\n        print(f'{i}. {s[\"name\"]}: {s[\"score\"]}分')\n\ndef save_data():\n    '''保存到JSON文件'''\n    with open('students.json', 'w', encoding='utf-8') as f:\n        json.dump(students, f, ensure_ascii=False, indent=2)\n    print('数据已保存')\n\n# 主菜单\nwhile True:\n    print('\\n1.添加 2.查看 3.保存 4.退出')\n    choice = input('选择: ')\n    if choice == '1': add_student()\n    elif choice == '2': show_all()\n    elif choice == '3': save_data()\n    elif choice == '4': break",
            "ask": "带我写一个完整的学生成绩管理系统，包含增删改查和排名功能"
        },
    }
    topic_id = request.args.get("id", "")
    if topic_id and topic_id in lessons:
        return jsonify({"lesson": lessons[topic_id]})
    return jsonify({"lessons": lessons})


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
