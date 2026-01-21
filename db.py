import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS hosts (
    host_id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    is_premium INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS anon_users (
    anon_id TEXT,
    host_id INTEGER,
    telegram_id INTEGER,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    PRIMARY KEY (anon_id, host_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anon_id TEXT,
    host_id INTEGER,
    text TEXT,
    created_at TEXT
);
""")

conn.commit()
