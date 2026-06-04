# -*- coding: utf-8 -*-
"""
蟒蛇老师教Python - Tkinter 桌面 GUI 应用

技术扩展: 图形界面开发 (Tkinter)
支持: 流式对话 / 表情面板 / 现代化配色

运行: python app_gui.py
"""

import os, sys, threading, tkinter as tk
from tkinter import scrolledtext, messagebox
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chatbot_core import ChatBot

# 常用表情列表（50个）
EMOJI_PANEL = [
    "😀","😂","🤣","😊","😍","🤔","😅","😢","😎","🥳",
    "👍","👎","👏","💪","🙏","❤","🔥","🎉","🌟","✨",
    "🐍","💻","📚","💡","✅","❌","⏰","🌈","🎵","🍵",
    "☕","🍰","🎂","🚀","⭐","🏆","💯","🤖","👋","😱",
    "🙂","😋","🤩","😤","🥺","😴","🤗","🙃","😜","🫡",
]


class ChatAppGUI:
    """蟒蛇老师教Python - 桌面教学应用"""

    # 配色方案: 丛林绿 + Python 蓝黄
    C = {
        "bg":        "#f0f4ee",  # 主背景
        "header":    "#1b4332",  # 深绿
        "primary":   "#2d6a4f",  # 蟒蛇绿
        "accent":    "#52b788",  # 浅绿
        "blue":      "#306998",  # Python 蓝
        "yellow":    "#ffd43b",  # Python 黄
        "white":     "#ffffff",
        "text":      "#2d3a2d",
        "text_dim":  "#888888",
        "user_bg":   "#306998",
        "bot_bg":    "#f5faf5",
        "bot_border":"#52b788",
        "input_bg":  "#f8faf5",
        "danger":    "#d32f2f",
    }

    def __init__(self):
        self.bot = ChatBot()

        self.root = tk.Tk()
        self.root.title("蟒蛇老师教Python")
        self.root.geometry("750x650")
        self.root.minsize(550, 450)
        self.root.configure(bg=self.C["bg"])

        self._create_header()
        self._create_chat_area()
        self._create_emoji_bar()
        self._create_input_area()
        self._create_status_bar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.input_entry.bind("<Return>", self._on_enter_key)

        self._display_welcome()
        self._update_status(f"蟒蛇老师已就绪 | 知识库 {len(self.bot.knowledge_base)} 个话题")

    # ================================================================
    # 界面构建
    # ================================================================

    def _create_header(self):
        """顶部标题栏"""
        h = tk.Frame(self.root, bg=self.C["header"], height=52)
        h.pack(fill=tk.X)
        h.pack_propagate(False)

        # 蟒蛇图标 + 标题
        title = tk.Label(
            h, text="🐍  蟒蛇老师教Python",
            font=("Microsoft YaHei", 16, "bold"),
            fg=self.C["yellow"], bg=self.C["header"],
        )
        title.pack(side=tk.LEFT, padx=18, pady=10)

        # 右侧小字
        ver = tk.Label(
            h, text="Python Teacher",
            font=("Microsoft YaHei", 9),
            fg=self.C["accent"], bg=self.C["header"],
        )
        ver.pack(side=tk.RIGHT, padx=18, pady=10)

    def _create_chat_area(self):
        """聊天消息显示区"""
        cf = tk.Frame(self.root, bg=self.C["bg"])
        cf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

        self.chat_display = scrolledtext.ScrolledText(
            cf, wrap=tk.WORD,
            font=("Microsoft YaHei", 10),
            bg=self.C["white"], fg=self.C["text"],
            state=tk.DISABLED,
            relief=tk.FLAT, borderwidth=1,
            padx=14, pady=10,
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # 标签样式
        self.chat_display.tag_config("user_label",
            foreground=self.C["blue"],
            font=("Microsoft YaHei", 10, "bold"))
        self.chat_display.tag_config("bot_label",
            foreground=self.C["primary"],
            font=("Microsoft YaHei", 10, "bold"))
        self.chat_display.tag_config("user_msg",
            foreground=self.C["text"],
            font=("Microsoft YaHei", 10),
            lmargin1=24, lmargin2=24, spacing3=10)
        self.chat_display.tag_config("bot_msg",
            foreground="#1a3a1a",
            font=("Microsoft YaHei", 10),
            lmargin1=24, lmargin2=24, spacing3=10)
        self.chat_display.tag_config("system_msg",
            foreground=self.C["text_dim"],
            font=("Microsoft YaHei", 9))

    def _create_emoji_bar(self):
        """表情面板"""
        ef = tk.Frame(self.root, bg=self.C["bg"])
        ef.pack(fill=tk.X, padx=12)

        label = tk.Label(ef, text="表情:", font=("Microsoft YaHei", 9),
                         fg=self.C["text_dim"], bg=self.C["bg"])
        label.pack(side=tk.LEFT, padx=(0, 6))

        # 创建可滚动的表情按钮区
        emoji_frame = tk.Frame(ef, bg=self.C["bg"])
        emoji_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        for emoji in EMOJI_PANEL:
            btn = tk.Button(
                emoji_frame, text=emoji,
                font=("Segoe UI Emoji", 14),
                relief=tk.FLAT, bg=self.C["bg"],
                cursor="hand2",
                activebackground=self.C["accent"],
                command=lambda e=emoji: self._insert_emoji(e),
            )
            btn.pack(side=tk.LEFT, padx=1)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#d8e8d8"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=self.C["bg"]))

    def _create_input_area(self):
        """输入区"""
        inf = tk.Frame(self.root, bg=self.C["bg"])
        inf.pack(fill=tk.X, padx=12, pady=(6, 10))

        # 输入框
        self.input_entry = tk.Entry(
            inf, font=("Microsoft YaHei", 12),
            relief=tk.FLAT, borderwidth=0,
            bg=self.C["input_bg"],
            insertbackground=self.C["primary"],
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                              ipady=8, padx=(0, 8))
        # 用 Frame 模拟圆角边框
        self.input_entry.bind("<FocusIn>",
            lambda e: self.input_entry.config(bg=self.C["white"]))
        self.input_entry.bind("<FocusOut>",
            lambda e: self.input_entry.config(bg=self.C["input_bg"]))
        self.input_entry.focus_set()

        # 发送按钮
        send_btn = tk.Button(
            inf, text="发 送",
            command=self._send_message,
            font=("Microsoft YaHei", 11, "bold"),
            bg=self.C["primary"], fg=self.C["white"],
            relief=tk.FLAT, cursor="hand2",
            padx=22, pady=6,
            activebackground="#1b4332", activeforeground="white",
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.bind("<Enter>", lambda e: send_btn.config(bg="#1b4332"))
        send_btn.bind("<Leave>", lambda e: send_btn.config(bg=self.C["primary"]))

    def _create_status_bar(self):
        """状态栏"""
        sf = tk.Frame(self.root, bg="#e0e4dd", height=22)
        sf.pack(fill=tk.X, side=tk.BOTTOM)
        sf.pack_propagate(False)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(sf, textvariable=self.status_var,
                 font=("Microsoft YaHei", 8),
                 bg="#e0e4dd", fg="#777",
                 anchor=tk.W, padx=12).pack(fill=tk.X)

    # ================================================================
    # 交互逻辑
    # ================================================================

    def _insert_emoji(self, emoji):
        """插入表情到输入框"""
        pos = self.input_entry.index(tk.INSERT)
        self.input_entry.insert(pos, emoji)
        self.input_entry.focus_set()

    def _display_welcome(self):
        """欢迎消息"""
        msg = "🐍  欢迎来到蟒蛇老师的Python课堂！输入你的问题，开始学习吧~\n\n"
        self._append_to_display(msg, "system_msg")

    def _append_to_display(self, text, tag=None):
        """追加文本到聊天区"""
        self.chat_display.config(state=tk.NORMAL)
        if tag:
            self.chat_display.insert(tk.END, text, tag)
        else:
            self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _send_message(self):
        """发送消息（流式）"""
        user_input = self.input_entry.get().strip()
        if not user_input:
            return

        self.input_entry.delete(0, tk.END)
        self.input_entry.config(state=tk.DISABLED)

        now = datetime.now().strftime("%H:%M")
        self._append_to_display(f"\n🍵 你 [{now}]\n", "user_label")
        self._append_to_display(f"{user_input}\n", "user_msg")

        self._update_status("🐍 思考中...")
        self.root.update_idletasks()

        now = datetime.now().strftime("%H:%M")
        self._append_to_display(f"\n🐍 蟒蛇老师 [{now}]\n", "bot_label")

        def stream_reply():
            try:
                for chunk in self.bot.get_response_stream(user_input):
                    self.root.after(0, self._append_stream_chunk, chunk)
                self.root.after(0, self._stream_done)
            except Exception as e:
                self.root.after(0, self._display_error, str(e))

        threading.Thread(target=stream_reply, daemon=True).start()

    def _append_stream_chunk(self, chunk):
        self._append_to_display(chunk, "bot_msg")

    def _stream_done(self):
        self._append_to_display("\n", "bot_msg")
        self._append_to_display("─" * 50 + "\n", "system_msg")
        self._update_status(f"就绪 | 共 {len(self.bot.chat_history)} 条消息")
        self.input_entry.config(state=tk.NORMAL)
        self.input_entry.focus_set()

    def _display_error(self, error_msg):
        self._append_to_display(f"\n错误: {error_msg}\n", "system_msg")
        self._update_status("发生错误")
        self.input_entry.config(state=tk.NORMAL)
        self.input_entry.focus_set()

    def _on_enter_key(self, event):
        self._send_message()

    # ================================================================
    # 菜单功能
    # ================================================================

    def _export_history(self):
        try:
            path = self.bot.export_history_to_txt()
            messagebox.showinfo("导出成功", f"聊天记录已导出到:\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _clear_history(self):
        if not messagebox.askyesno("确认", "确定要清空所有聊天记录吗？"):
            return
        self.bot.clear_history()
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self._display_welcome()
        self._update_status("聊天记录已清空")

    def _show_stats(self):
        s = self.bot.get_statistics()
        info = (
            f"总消息数:     {s['total_messages']}\n"
            f"用户消息:     {s['user_messages']}\n"
            f"机器人消息:   {s['bot_messages']}\n"
            f"知识库话题:   {s['knowledge_base_topics']}\n"
            f"停用词数量:   {s['stop_words_count']}\n"
            f"API 模型:     {s['api_model']}\n"
            f"API 状态:     {'已连接' if s['api_enabled'] else '未连接'}"
        )
        messagebox.showinfo("统计信息", info)

    def _show_about(self):
        messagebox.showinfo("关于",
            "蟒蛇老师教Python v2.0\n\n"
            "AI编程教学聊天机器人\n"
            "DeepSeek-V3 + Python + Tkinter\n\n"
            "功能: 流式对话 · 15个知识点 · 自测 · 刷题\n"
            "数据结构: list | dict | set | tuple\n"
            "文件读写: JSON | TXT\n"
            "数据库: SQLite\n"
            "第三方库: requests | jieba | flask"
        )

    def _show_help(self):
        messagebox.showinfo("使用帮助",
            "[蟒蛇老师教Python - 使用帮助]\n\n"
            "1. 在输入框中输入Python相关问题\n"
            '2. 按 Enter 或点击「发送」\n'
            "3. 蟒蛇老师会流式逐字回复\n\n"
            "表情面板: 点击表情按钮插入Emoji\n"
            "Web端更多功能:\n"
            "  学习路线 · 自测 · 编程刷题 · 个人中心\n"
            "  访问 http://127.0.0.1:5000"
        )

    def _update_status(self, text):
        self.status_var.set(text)

    def _on_close(self):
        self.bot.save_chat_history()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print("=" * 50)
    print("蟒蛇老师教Python - Tkinter GUI")
    print("=" * 50)
    print("正在启动...")
    app = ChatAppGUI()
    app.run()
