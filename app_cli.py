# -*- coding: utf-8 -*-
"""
蟒蛇老师教Python - 命令行入口

这是聊天机器人的命令行版本，提供最基础的交互功能。
在终端中运行 python app_cli.py 即可开始聊天对话。

命令列表:
    /help   - 显示帮助信息
    /stats  - 显示聊天统计
    /export - 导出聊天记录为TXT文件
    /clear  - 清空聊天记录
    /quit   - 退出程序
"""

import os
import sys

# 将当前目录添加到模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot_core import ChatBot


def safe_print(text, end="\n", flush=False):
    """安全打印，处理 Windows 控制台 GBK 编码限制"""
    try:
        print(text, end=end, flush=flush)
    except (UnicodeEncodeError, UnicodeDecodeError):
        clean = text.encode("gbk", errors="replace").decode("gbk", errors="replace")
        print(clean, end=end, flush=flush)


def print_banner():
    """打印欢迎横幅（使用纯 ASCII 字符避免编码问题）"""
    banner = """
    ==============================================
         蟒蛇老师教Python v1.0
    ==============================================
    命令:
      /help    - 显示帮助信息
      /stats   - 显示聊天统计
      /export  - 导出聊天记录到TXT
      /clear   - 清空聊天记录
      /quit    - 退出程序
    ==============================================
    """
    safe_print(banner)


def handle_command(bot, cmd):
    """
    处理特殊命令

    Args:
        bot: ChatBot 实例
        cmd: 命令字符串

    Returns:
        bool: True 表示继续对话，False 表示退出程序
    """
    if cmd == "/help":
        safe_print("\n[帮助] 可用命令:")
        safe_print("  /help   - 显示此帮助信息")
        safe_print("  /stats  - 显示聊天统计信息")
        safe_print("  /export - 导出聊天记录为 TXT 文件")
        safe_print("  /clear  - 清空所有聊天记录")
        safe_print("  /quit   - 退出程序")
        safe_print("\n直接输入文字即可与机器人对话！")
        return True

    elif cmd == "/stats":
        stats = bot.get_statistics()
        safe_print("\n[统计信息]")
        safe_print(f"  总消息数:    {stats['total_messages']}")
        safe_print(f"  用户消息:    {stats['user_messages']}")
        safe_print(f"  机器人消息:  {stats['bot_messages']}")
        safe_print(f"  知识库话题:  {stats['knowledge_base_topics']}")
        safe_print(f"  停用词数量:  {stats['stop_words_count']}")
        safe_print(f"  规则匹配:    {'开启' if stats['rule_enabled'] else '关闭'}")
        safe_print(f"  API 调用:    {'开启' if stats['api_enabled'] else '关闭'}")
        return True

    elif cmd == "/export":
        filepath = bot.export_history_to_txt()
        safe_print(f"[导出] 聊天记录已保存到: {filepath}")
        return True

    elif cmd == "/clear":
        confirm = input("确认清空所有聊天记录？(y/n): ").strip().lower()
        if confirm == "y":
            bot.clear_history()
            safe_print("[清空] 聊天记录已清空。")
        else:
            safe_print("[取消] 操作已取消。")
        return True

    elif cmd == "/quit":
        safe_print("\n再见！期待下次聊天~")
        return False

    else:
        safe_print(f"[错误] 未知命令: {cmd}")
        safe_print("输入 /help 查看可用命令。")
        return True


def main():
    """
    主函数：命令行聊天循环

    实现 "输入 → 处理 → 输出" 的完整功能闭环
    """
    # 设置控制台为 UTF-8 模式（Windows 兼容）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print_banner()

    # 初始化聊天机器人
    bot = ChatBot()
    safe_print(f"\n[就绪] 知识库已加载 {len(bot.knowledge_base)} 个话题，可以开始对话！")
    safe_print("输入 /help 查看命令，直接输入文字开始聊天。\n")

    # 主对话循环 —— "输入 → 处理 → 输出" 闭环
    running = True
    while running:
        try:
            # 步骤1: 接收用户输入
            user_input = input("\n你: ").strip()

            # 处理空输入
            if not user_input:
                continue

            # 步骤2: 判断是否为命令
            if user_input.startswith("/"):
                # 处理命令
                running = handle_command(bot, user_input)
            else:
                # 步骤2+3: 流式处理 + 逐字输出
                safe_print(f"\n蟒蛇老师: ", end="")
                for chunk in bot.get_response_stream(user_input):
                    safe_print(chunk, end="", flush=True)
                safe_print("")  # 换行

        except KeyboardInterrupt:
            # 用户按 Ctrl+C 退出
            safe_print("\n\n[提示] 检测到 Ctrl+C，输入 /quit 退出程序。")
        except EOFError:
            safe_print("\n再见！")
            break
        except Exception as e:
            safe_print(f"\n[错误] 发生异常: {e}")
            safe_print("请重试，或输入 /quit 退出。")

    safe_print("程序已退出。")


if __name__ == "__main__":
    main()
