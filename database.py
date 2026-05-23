import sqlite3
import json
from datetime import date

DB_PATH = "max_users.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            sender          TEXT PRIMARY KEY,
            name            TEXT,
            first_seen      TEXT NOT NULL,
            message_count   INTEGER DEFAULT 0,
            daily_count     INTEGER DEFAULT 0,
            last_msg_date   TEXT,
            is_paid         INTEGER DEFAULT 0,
            memory          TEXT DEFAULT '[]',
            onboarded       INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            sender      TEXT PRIMARY KEY,
            messages    TEXT DEFAULT '[]',
            document    TEXT DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender      TEXT,
            message     TEXT,
            timestamp   TEXT
        )
    """)

    conn.commit()
    conn.close()


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_user(sender):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE sender=?", (sender,)).fetchone()
    conn.close()
    return dict(row) if row else None


def ensure_user(sender):
    today = str(date.today())
    conn = _get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO users (sender, first_seen, last_msg_date)
        VALUES (?, ?, ?)
    """, (sender, today, today))
    conn.commit()
    conn.close()
    return get_user(sender)


def tick_message(sender):
    """Increment counters, reset daily on new day. Returns (user, is_new_user)."""
    user = get_user(sender)
    is_new = user is None

    if is_new:
        user = ensure_user(sender)

    today = str(date.today())
    conn = _get_conn()

    if user["last_msg_date"] != today:
        conn.execute("""
            UPDATE users
            SET daily_count=1, message_count=message_count+1, last_msg_date=?
            WHERE sender=?
        """, (today, sender))
    else:
        conn.execute("""
            UPDATE users
            SET daily_count=daily_count+1, message_count=message_count+1
            WHERE sender=?
        """, (sender,))

    conn.commit()
    conn.close()
    return get_user(sender), is_new


def is_over_limit(sender, limit=20):
    user = get_user(sender)
    if not user or user["is_paid"]:
        return False
    if user["last_msg_date"] != str(date.today()):
        return False
    return user["daily_count"] >= limit


def update_user(sender, **kwargs):
    if not kwargs:
        return
    conn = _get_conn()
    clause = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE users SET {clause} WHERE sender=?", (*kwargs.values(), sender))
    conn.commit()
    conn.close()


# ---- MEMORY ----

def add_memory(sender, fact):
    user = get_user(sender) or ensure_user(sender)
    mem = json.loads(user["memory"] or "[]")
    mem.append(fact)
    if len(mem) > 20:
        mem = mem[-20:]
    update_user(sender, memory=json.dumps(mem))


def get_memory(sender):
    user = get_user(sender)
    return json.loads(user["memory"] or "[]") if user else []


# ---- CONVERSATIONS ----

def save_conversation(sender, messages):
    conn = _get_conn()
    conn.execute("""
        INSERT INTO conversations (sender, messages)
        VALUES (?, ?)
        ON CONFLICT(sender) DO UPDATE SET messages=excluded.messages
    """, (sender, json.dumps(messages)))
    conn.commit()
    conn.close()


def load_conversation(sender):
    conn = _get_conn()
    row = conn.execute("SELECT messages FROM conversations WHERE sender=?", (sender,)).fetchone()
    conn.close()
    return json.loads(row["messages"]) if row else []


def save_document(sender, text):
    conn = _get_conn()
    conn.execute("""
        INSERT INTO conversations (sender, document)
        VALUES (?, ?)
        ON CONFLICT(sender) DO UPDATE SET document=excluded.document
    """, (sender, text))
    conn.commit()
    conn.close()


def load_document(sender):
    conn = _get_conn()
    row = conn.execute("SELECT document FROM conversations WHERE sender=?", (sender,)).fetchone()
    conn.close()
    return row["document"] if row else ""


# ---- LEADS ----

def save_lead(sender, message):
    from datetime import datetime
    conn = _get_conn()
    conn.execute(
        "INSERT INTO leads (sender, message, timestamp) VALUES (?, ?, ?)",
        (sender, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_all_senders():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT sender FROM users WHERE sender NOT LIKE '%status%' AND sender NOT LIKE '%broadcast%'"
    ).fetchall()
    conn.close()
    return [r["sender"] for r in rows]


def get_stats():
    from datetime import date
    today = str(date.today())
    conn  = _get_conn()
    total_users   = conn.execute("SELECT COUNT(*) FROM users WHERE sender NOT LIKE '%status%' AND sender NOT LIKE '%broadcast%'").fetchone()[0]
    active_today  = conn.execute("SELECT COUNT(*) FROM users WHERE last_msg_date=? AND sender NOT LIKE '%status%' AND sender NOT LIKE '%broadcast%'", (today,)).fetchone()[0]
    total_msgs    = conn.execute("SELECT SUM(message_count) FROM users WHERE sender NOT LIKE '%status%' AND sender NOT LIKE '%broadcast%'").fetchone()[0] or 0
    total_leads   = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    paid_users    = conn.execute("SELECT COUNT(*) FROM users WHERE is_paid=1").fetchone()[0]
    conn.close()
    return {
        "total_users":  total_users,
        "active_today": active_today,
        "total_msgs":   total_msgs,
        "total_leads":  total_leads,
        "paid_users":   paid_users
    }


def get_recent_leads(limit=20):
    conn = _get_conn()
    rows = conn.execute(
        """SELECT l.sender, l.message, l.timestamp, u.name
           FROM leads l
           LEFT JOIN users u ON l.sender = u.sender
           ORDER BY l.id DESC LIMIT ?""", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_users(limit=20):
    conn = _get_conn()
    rows = conn.execute(
        """SELECT sender, name, first_seen, message_count, daily_count, is_paid 
           FROM users 
           WHERE sender NOT LIKE '%status%' 
           AND sender NOT LIKE '%broadcast%'
           ORDER BY first_seen DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_message_stats(days=14):
    conn = _get_conn()
    rows = conn.execute("""
        SELECT last_msg_date as date, SUM(daily_count) as messages
        FROM users
        GROUP BY last_msg_date
        ORDER BY last_msg_date DESC
        LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]