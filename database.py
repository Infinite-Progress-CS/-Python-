# -*- coding: utf-8 -*-
"""
数据库模块 - SQLite

表结构:
    users: 用户表 (id, username, created_at)
    conversations: 会话表 (id, user_id, title, created_at)
    messages: 消息表 (id, conversation_id, role, content, created_at)

数据结构: list(查询结果), dict(行数据), tuple(表结构定义)
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatbot.db")


def get_conn():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 返回 dict-like 行
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL DEFAULT '',
            avatar TEXT DEFAULT '\U0001F40D',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '新对话',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
    """)
    conn.commit()
    conn.close()


# ======== 用户操作 ========

def login_or_register(username, password):
    """
    登录或注册用户
    返回 (success, user_id, is_new, error_msg)
    """
    conn = get_conn()
    cur = conn.execute("SELECT id, password FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    if row:
        # 老用户：验证密码
        if row["password"] == password:
            conn.close()
            return True, row["id"], False, ""
        else:
            conn.close()
            return False, None, False, "密码错误"
    else:
        # 新用户：注册
        if len(password) < 3:
            conn.close()
            return False, None, False, "密码至少3位"
        cur = conn.execute(
            "INSERT INTO users (username, password, avatar) VALUES (?, ?, '\U0001F40D')",
            (username, password)
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return True, user_id, True, ""


def get_user_profile(user_id):
    """获取用户信息"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, avatar, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "username": row["username"],
                "avatar": row["avatar"], "created_at": row["created_at"]}
    return None


def update_avatar(user_id, avatar):
    """更新用户头像"""
    conn = get_conn()
    conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, user_id))
    conn.commit()
    conn.close()


def get_user_stats(user_id):
    """获取用户统计"""
    conn = get_conn()
    total_convs = conn.execute(
        "SELECT COUNT(*) as c FROM conversations WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    total_msgs = conn.execute(
        "SELECT COUNT(*) as c FROM messages m "
        "JOIN conversations c ON m.conversation_id = c.id "
        "WHERE c.user_id = ?", (user_id,)
    ).fetchone()["c"]
    conn.close()
    return {"total_conversations": total_convs, "total_messages": total_msgs}


# ======== 会话操作 ========

def create_conversation(user_id, title="新对话"):
    """创建新会话，返回 conversation_id"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
        (user_id, title)
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def get_conversations(user_id):
    """
    获取用户的所有会话列表 (list of dict)
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, created_at FROM conversations "
        "WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "title": r["title"],
             "created_at": r["created_at"]} for r in rows]


def update_conversation_title(conv_id, title):
    """更新会话标题（取用户第一句话前20字）"""
    conn = get_conn()
    conn.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        (title, conv_id)
    )
    conn.commit()
    conn.close()


def delete_conversation(conv_id):
    """删除会话及其消息"""
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


# ======== 消息操作 ========

def add_message(conv_id, role, content):
    """添加一条消息"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conv_id, role, content)
    )
    conn.commit()
    conn.close()


def get_messages(conv_id):
    """
    获取会话的所有消息 (list of dict)
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"],
             "time": r["created_at"]} for r in rows]


def get_conversation_owner(conv_id):
    """获取会话的所属用户ID"""
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    conn.close()
    return row["user_id"] if row else None


# 初始化
init_db()
# 兼容旧库：添加 avatar 列
try:
    conn = get_conn()
    conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT 'snake'")
    conn.commit(); conn.close()
except:
    pass
