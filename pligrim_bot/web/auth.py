"""Telegram Mini App verification and one-time browser sign-in, shared by bot and web."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl
from pligrim_bot.config.constants import API_TOKEN,PROJECT_ROOT


def state_dir():
    path=Path(os.getenv('WEB_STATE_DIR',str(Path(PROJECT_ROOT)/'data/runtime')))
    path.mkdir(parents=True,exist_ok=True)
    return path


@contextmanager
def database():
    conn=sqlite3.connect(state_dir()/'web.sqlite3',timeout=20)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS logins(id TEXT PRIMARY KEY, secret TEXT NOT NULL, user TEXT, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS downloads(token TEXT PRIMARY KEY, job TEXT NOT NULL, owner INTEGER NOT NULL, file_index INTEGER NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner INTEGER NOT NULL, request_key TEXT NOT NULL,
          status TEXT NOT NULL, payload TEXT NOT NULL, files TEXT NOT NULL DEFAULT '[]',
          sent INTEGER NOT NULL DEFAULT 0, error TEXT, created REAL NOT NULL, UNIQUE(owner,request_key));
    ''')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def check_allowed(user):
    allowed={int(v) for v in os.getenv('ALLOWED_USER_IDS','').replace(',',' ').split() if v.isdigit()}
    if allowed and user['id'] not in allowed:raise ValueError('Нет доступа к сервису. Обратитесь к администратору.')
    return {'id':int(user['id']),'first_name':str(user.get('first_name',''))[:100],'username':str(user.get('username',''))[:100]}


def verify_init_data(raw,now=None):
    if not raw or len(raw)>16384:raise ValueError('Откройте мини-приложение через Telegram')
    pairs=parse_qsl(raw,keep_blank_values=True)
    fields=dict(pairs)
    if len(fields)!=len(pairs):raise ValueError('Некорректные данные Telegram')
    signature=fields.pop('hash','')
    check='\n'.join(f'{key}={value}' for key,value in sorted(fields.items()))
    secret=hmac.new(b'WebAppData',API_TOKEN.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):raise ValueError('Не удалось проверить подпись Telegram')
    current=now if now is not None else time.time()
    try:
        age=current-int(fields['auth_date'])
        user=json.loads(fields['user'])
        if not isinstance(user['id'],int) or user['id']<=0:raise ValueError()
    except (KeyError,TypeError,ValueError,json.JSONDecodeError):raise ValueError('Некорректные данные Telegram') from None
    if age< -30 or age>3600:raise ValueError('Сессия Telegram устарела. Откройте приложение заново.')
    return check_allowed(user)


def new_session(user):
    user=check_allowed(user);token=secrets.token_urlsafe(32)
    with database() as db:
        db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),json.dumps(user),time.time()+86400))
    return token


def session_user(token):
    if not token:return None
    with database() as db:
        row=db.execute('SELECT user FROM sessions WHERE token=? AND expires>?',(digest(token),time.time())).fetchone()
    return check_allowed(json.loads(row['user'])) if row else None


def new_challenge():
    key=secrets.token_urlsafe(24);secret=secrets.token_urlsafe(32)
    with database() as db:
        db.execute('DELETE FROM logins WHERE expires<?',(time.time(),))
        if db.execute('SELECT COUNT(*) FROM logins').fetchone()[0]>500:raise ValueError('Слишком много запросов. Попробуйте позже.')
        db.execute('INSERT INTO logins VALUES(?,?,NULL,?)',(key,digest(secret),time.time()+300))
    return key,secret


def approve_challenge(key,user):
    user=check_allowed(user)
    with database() as db:
        updated=db.execute('UPDATE logins SET user=? WHERE id=? AND expires>? AND user IS NULL',(json.dumps(user),key,time.time())).rowcount
    if not updated:raise ValueError('Ссылка для входа устарела или уже использована. Откройте сайт заново.')


def consume_challenge(key,secret):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM logins WHERE id=? AND expires>?',(key,time.time())).fetchone()
        if not row or not hmac.compare_digest(row['secret'],digest(secret)):raise ValueError('Ссылка для входа устарела')
        if not row['user']:return None
        db.execute('DELETE FROM logins WHERE id=?',(key,))
        return check_allowed(json.loads(row['user']))
