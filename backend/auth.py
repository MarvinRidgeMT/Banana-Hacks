"""Accounts for Cold Case: sign up / sign in, per-user case lists, and request limits.

Security choices
  * Passwords: scrypt (N=2^14, r=8, p=1) with a random 16-byte salt per user; compared in constant time.
  * Sessions: 256-bit random tokens sent as `Authorization: Bearer <token>`. Only the SHA-256 of a
    token is stored, so a leaked database can't be replayed. Tokens expire after 30 days.
  * Rate limits per client IP: sign-in/sign-up 10 per 10 min, uploads 30 per hour.
  * Accounts are optional: the demos and the restorer work signed out; signing in keeps
    "My cases" on the server, separate for each person, on any device.
Storage: SQLite file next to the cache (CV_AUTH_DB), created on first use.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

DB_PATH = Path(os.environ.get("CV_AUTH_DB", Path(__file__).resolve().parent.parent / "accounts.sqlite3"))
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, salt BLOB NOT NULL, pw BLOB NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
            expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS cases(user_id INTEGER NOT NULL, key TEXT NOT NULL, title TEXT NOT NULL,
            kind TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(user_id, key));
    """)
    return con


_con: sqlite3.Connection | None = None


def con() -> sqlite3.Connection:
    global _con
    if _con is None:
        _con = _db()
    return _con


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthError(ValueError):
    pass


def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        con().execute("INSERT INTO sessions VALUES(?,?,?)", (_token_hash(token), user_id, time.time() + SESSION_DAYS * 86400))
        con().execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        con().commit()
    return token


def signup(email: str, password: str, name: str) -> tuple[str, dict]:
    email = (email or "").strip().lower()
    name = (name or "").strip()[:60] or email.split("@")[0]
    if not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email address.")
    if len(password or "") < 8 or len(password) > 200:
        raise AuthError("Use a password of at least 8 characters.")
    if password.lower() in {"password", "12345678", "123456789", "qwertyui", "password1"}:
        raise AuthError("That password is too common. Pick another.")
    salt = secrets.token_bytes(16)
    pw = _hash_pw(password, salt)
    with _lock:
        try:
            cur = con().execute("INSERT INTO users(email,name,salt,pw,created) VALUES(?,?,?,?,?)",
                                (email, name, salt, pw, time.time()))
            con().commit()
        except sqlite3.IntegrityError:
            raise AuthError("An account with that email already exists. Sign in instead.")
    uid = cur.lastrowid
    return _new_session(uid), {"email": email, "name": name}


def login(email: str, password: str) -> tuple[str, dict]:
    email = (email or "").strip().lower()
    row = con().execute("SELECT id,name,salt,pw FROM users WHERE email=?", (email,)).fetchone()
    # hash even when the user doesn't exist, so timing doesn't reveal which emails have accounts
    salt = row[2] if row else b"\0" * 16
    ok = hmac.compare_digest(_hash_pw(password or "", salt), row[3] if row else b"\1" * 32)
    if not row or not ok:
        raise AuthError("Wrong email or password.")
    return _new_session(row[0]), {"email": email, "name": row[1]}


def user_for(token: str | None) -> dict | None:
    if not token:
        return None
    row = con().execute(
        "SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",
        (_token_hash(token), time.time())).fetchone()
    return {"id": row[0], "email": row[1], "name": row[2]} if row else None


def logout(token: str) -> None:
    with _lock:
        con().execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
        con().commit()


def list_cases(user_id: int) -> list[dict]:
    rows = con().execute("SELECT key,title,kind,at FROM cases WHERE user_id=? ORDER BY at DESC LIMIT 200", (user_id,))
    return [{"key": k, "title": t, "kind": kd, "at": int(a * 1000)} for k, t, kd, a in rows]


def add_case(user_id: int, key: str, title: str, kind: str) -> None:
    with _lock:
        con().execute("INSERT INTO cases VALUES(?,?,?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET at=excluded.at",
                      (user_id, key, (title or "Restored photo")[:120], "document" if kind == "document" else "photo", time.time()))
        con().commit()


def remove_case(user_id: int, key: str | None) -> None:
    with _lock:
        if key:
            con().execute("DELETE FROM cases WHERE user_id=? AND key=?", (user_id, key))
        else:
            con().execute("DELETE FROM cases WHERE user_id=?", (user_id,))
        con().commit()


# ---------------- rate limiting (in memory, per client IP) ----------------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def allow_n(ip: str, bucket: str, n: int, limit: int, window_s: float) -> bool:
    """Take n units from the bucket at once (all or nothing), e.g. one per photo in a batch."""
    now = time.time()
    q = _hits[(bucket, ip)]
    while q and q[0] < now - window_s:
        q.popleft()
    if len(q) + n > limit:
        return False
    q.extend([now] * n)
    return True


def allow(ip: str, bucket: str, limit: int, window_s: float) -> bool:
    now = time.time()
    q = _hits[(bucket, ip)]
    while q and q[0] < now - window_s:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
