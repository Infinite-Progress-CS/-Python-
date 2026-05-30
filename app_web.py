# -*- coding: utf-8 -*-
"""
蟒蛇老师教Python - Flask Web 应用

技术扩展1: Web应用开发 (Flask)

提供基于浏览器的聊天界面，支持：
- 美观的 Web 聊天界面
- AJAX 异步通信，无需刷新页面
- 与核心 ChatBot 引擎无缝集成

运行方式:
    python app_web.py
    然后在浏览器中访问: http://127.0.0.1:5000
"""

import json
import os
import sys

# 将当前目录添加到模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, Response
from chatbot_core import ChatBot

# 创建 Flask 应用实例
app = Flask(__name__)
app.config["SECRET_KEY"] = "chatbot-secret-key-2024"

# 创建聊天机器人实例（全局单例）
bot = ChatBot()


@app.route("/")
def index():
    """
    主页路由：返回聊天页面

    Returns:
        HTML 页面
    """
    return render_template("chat.html")


# 禁用缓存（确保前端 JS/CSS 总是最新）
@app.after_request
def add_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    聊天 API 接口

    接收用户消息的 JSON 数据，返回机器人的回复。
    实现 "输入 → 处理 → 输出" 的 Web 版本闭环。

    请求格式:
        {"message": "用户输入文本"}

    响应格式:
        {"reply": "机器人回复文本", "time": "时间戳"}

    Returns:
        JSON 响应
    """
    # 获取请求数据（dict）
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"error": "请提供消息内容"}), 400

    user_message = data["message"].strip()

    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    # 核心处理: 调用 ChatBot 获取回复
    reply = bot.get_response(user_message)

    # 获取最后一条消息的时间
    last_msg_time = ""
    if bot.chat_history:
        last_msg_time = bot.chat_history[-1].get("time", "")

    # 构建响应（dict 结构）
    response = {
        "reply": reply,
        "time": last_msg_time,
        "status": "success",
    }

    return jsonify(response)


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """
    流式聊天 API (SSE)

    接收用户消息，通过 Server-Sent Events 逐块推送回复。
    前端可以实时看到 AI 生成的每一个字。
    """
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "请提供消息内容"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    def generate():
        """SSE 事件生成器"""
        try:
            for chunk in bot.get_response_stream(user_message):
                # 每个chunk用SSE格式发送，确保中文不被转义
                payload = json.dumps(
                    {"chunk": chunk, "status": "streaming"},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
            yield "data: {\"chunk\": \"\", \"status\": \"done\"}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {{\"chunk\": \"出错了: {str(e)}\", \"status\": \"error\"}}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/history", methods=["GET"])
def api_history():
    """
    获取聊天历史 API

    Returns:
        JSON 格式的聊天记录列表
    """
    return jsonify({
        "history": bot.chat_history,
        "total": len(bot.chat_history),
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """
    获取统计信息 API

    Returns:
        JSON 格式的统计数据
    """
    stats = bot.get_statistics()
    return jsonify(stats)


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """
    清空聊天记录 API
    """
    bot.clear_history()
    return jsonify({"status": "success", "message": "聊天记录已清空"})


@app.route("/api/export", methods=["GET"])
def api_export():
    """
    导出聊天记录为 TXT API
    """
    filepath = bot.export_history_to_txt()
    return jsonify({
        "status": "success",
        "message": f"聊天记录已导出到: {filepath}",
        "filepath": filepath,
    })


# 错误处理
@app.errorhandler(404)
def not_found(error):
    """404 错误处理"""
    return jsonify({"error": "页面未找到"}), 404


@app.errorhandler(500)
def internal_error(error):
    """500 错误处理"""
    return jsonify({"error": "服务器内部错误"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("蟒蛇老师教Python - Web 应用")
    print("=" * 50)
    print(f"知识库已加载 {len(bot.knowledge_base)} 个话题")
    print("\n启动 Web 服务器...")
    print("请在浏览器中访问: http://127.0.0.1:5000")
    print("按 Ctrl+C 停止服务器\n")
    print("=" * 50)

    # 启动 Flask 开发服务器
    app.run(host="127.0.0.1", port=5000, debug=True)
