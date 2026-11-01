"""SQLite: схема и небольшие помощники."""
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    banned INTEGER NOT NULL DEFAULT 0,
    ban_reason TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    last_login INTEGER,
    lic_plan TEXT NOT NULL DEFAULT '',
    lic_expires INTEGER,
    lic_active INTEGER NOT NULL DEFAULT 0,
    max_devices INTEGER NOT NULL DEFAULT 1,
    usage_stats INTEGER NOT NULL DEFAULT 1,
    must_change_pw INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS license_keys(
    key TEXT PRIMARY KEY,
    plan TEXT NOT NULL,
    days INTEGER NOT NULL,
    max_devices INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    created_by INTEGER,
    note TEXT NOT NULL DEFAULT '',
    used_by INTEGER,
    used_at INTEGER,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS devices(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    hwid TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    last_version TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id, hwid)
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    user_id INTEGER,
    type TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_user ON events(user_id);
CREATE TABLE IF NOT EXISTS audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    admin_id INTEGER,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS login_attempts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    username TEXT NOT NULL,
    ip TEXT NOT NULL,
    ok INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts_ts ON login_attempts(ts);
CREATE TABLE IF NOT EXISTS announcements(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'info',
    pinned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS library(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '1',
    kind TEXT NOT NULL DEFAULT 'templates',
    count INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    downloads INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "maintenance": "0",
    "maintenance_text": "Идут технические работы. Попробуйте позже.",
    "min_version": "0.0.0.0",
    "latest_version": "",
    "download_url": "",
    "support_contact": "",
    "motd": "",
}


def now():
    return int(time.time())


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # journal по умолчанию: WAL ненадёжен на сетевых ФС хостингов
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_db(con):
    con.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
    con.commit()


def get_settings(con):
    return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM settings")}


def set_setting(con, key, value):
    con.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
