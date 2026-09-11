from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3, hashlib, secrets, os
from datetime import datetime

BASE = os.path.dirname(__file__)
DATA_DIR = os.environ.get('DATA_DIR', BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'lovebirdies.db')
app = FastAPI(title='LoveBirdies MVP')
app.mount('/static', StaticFiles(directory=os.path.join(BASE, 'static')), name='static')


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180_000).hex()
    return f'{salt}${digest}'


def verify_password(password, stored):
    salt, digest = stored.split('$', 1)
    return secrets.compare_digest(hash_password(password, salt).split('$', 1)[1], digest)


def init_db():
    c = conn()
    cur = c.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      name TEXT NOT NULL,
      age INTEGER NOT NULL,
      location TEXT NOT NULL,
      handicap REAL,
      gender TEXT DEFAULT '',
      interested_in TEXT DEFAULT '',
      looking_for TEXT DEFAULT 'Dating and seeing where it goes',
      bio TEXT DEFAULT '',
      golf_style TEXT DEFAULT 'Social golfer',
      home_club TEXT DEFAULT '',
      photo TEXT DEFAULT '',
      verified INTEGER DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_sessions(
      token TEXT PRIMARY KEY,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS likes(
      liker_id INTEGER NOT NULL,
      liked_id INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      UNIQUE(liker_id, liked_id)
    );
    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sender_id INTEGER NOT NULL,
      receiver_id INTEGER NOT NULL,
      body TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    ''')
    c.commit()
    c.close()


def remove_old_demo_accounts():
    demo_emails = (
        'aoife@example.com',
        'david@example.com',
        'sarah@example.com',
        'mark@example.com',
    )
    c = conn()
    cur = c.cursor()
    placeholders = ','.join('?' for _ in demo_emails)
    cur.execute(f'SELECT id FROM users WHERE email IN ({placeholders})', demo_emails)
    demo_ids = [row['id'] for row in cur.fetchall()]

    if demo_ids:
        id_placeholders = ','.join('?' for _ in demo_ids)
        cur.execute(
            f'DELETE FROM messages WHERE sender_id IN ({id_placeholders}) OR receiver_id IN ({id_placeholders})',
            demo_ids + demo_ids,
        )
        cur.execute(
            f'DELETE FROM likes WHERE liker_id IN ({id_placeholders}) OR liked_id IN ({id_placeholders})',
            demo_ids + demo_ids,
        )
        cur.execute(f'DELETE FROM sessions WHERE user_id IN ({id_placeholders})', demo_ids)
        cur.execute(f'DELETE FROM users WHERE id IN ({id_placeholders})', demo_ids)
        c.commit()

    c.close()


init_db()
remove_old_demo_accounts()


class Register(BaseModel):
    email: str
    password: str
    name: str
    age: int
    location: str
    handicap: Optional[float] = None
    gender: str = ''
    interested_in: str = ''
    looking_for: str = 'Dating and seeing where it goes'


class Login(BaseModel):
    email: str
    password: str


class AdminLogin(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    location: Optional[str] = None
    handicap: Optional[float] = None
    gender: Optional[str] = None
    interested_in: Optional[str] = None
    looking_for: Optional[str] = None
    bio: Optional[str] = None
    golf_style: Optional[str] = None
    home_club: Optional[str] = None
    photo: Optional[str] = None


class MessageIn(BaseModel):
    receiver_id: int
    body: str


def auth_user(authorization: Optional[str]):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Please log in')
    token = authorization[7:]
    c = conn()
    cur = c.cursor()
    cur.execute('SELECT user_id FROM sessions WHERE token=?', (token,))
    r = cur.fetchone()
    c.close()
    if not r:
        raise HTTPException(401, 'Session expired')
    return r['user_id']


def auth_admin(authorization: Optional[str]):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Admin login required')
    token = authorization[7:]
    c = conn()
    cur = c.cursor()
    cur.execute('SELECT token FROM admin_sessions WHERE token=?', (token,))
    r = cur.fetchone()
    c.close()
    if not r:
        raise HTTPException(401, 'Admin session expired')
    return True


def public_user(r):
    return {
        k: r[k]
        for k in [
            'id', 'name', 'age', 'location', 'handicap', 'gender',
            'interested_in', 'looking_for', 'bio', 'golf_style',
            'home_club', 'photo', 'verified'
        ]
    }


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def home():
    return FileResponse(os.path.join(BASE, 'static', 'index.html'))


@app.get('/admin')
def admin_page():
    return FileResponse(os.path.join(BASE, 'static', 'admin.html'))


@app.post('/api/admin/login')
def admin_login(data: AdminLogin):
    admin_email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    if not admin_email or not admin_password:
        raise HTTPException(503, 'Admin access has not been configured')

    email_ok = secrets.compare_digest(data.email.strip().lower(), admin_email)
    password_ok = secrets.compare_digest(data.password, admin_password)
    if not (email_ok and password_ok):
        raise HTTPException(401, 'Incorrect admin email or password')

    token = secrets.token_urlsafe(40)
    c = conn()
    c.execute('INSERT INTO admin_sessions(token,created_at) VALUES(?,?)', (token, datetime.utcnow().isoformat()))
    c.commit()
    c.close()
    return {'token': token}


@app.get('/api/admin/stats')
def admin_stats(authorization: Optional[str] = Header(None)):
    auth_admin(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute('SELECT COUNT(*) AS n FROM users')
    users = cur.fetchone()['n']
    cur.execute('SELECT COUNT(*) AS n FROM likes')
    likes = cur.fetchone()['n']
    cur.execute('''SELECT COUNT(*) AS n FROM likes a
                   JOIN likes b ON a.liker_id=b.liked_id AND a.liked_id=b.liker_id
                   WHERE a.liker_id < a.liked_id''')
    matches = cur.fetchone()['n']
    cur.execute('SELECT COUNT(*) AS n FROM messages')
    messages = cur.fetchone()['n']
    c.close()
    return {'users': users, 'likes': likes, 'matches': matches, 'messages': messages}


@app.get('/api/admin/users')
def admin_users(authorization: Optional[str] = Header(None)):
    auth_admin(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute('''
        SELECT
          u.id, u.name, u.email, u.age, u.location, u.handicap,
          u.gender, u.interested_in, u.looking_for, u.golf_style,
          u.home_club, u.verified, u.created_at,
          (SELECT COUNT(*) FROM likes l WHERE l.liker_id=u.id) AS likes_sent,
          (SELECT COUNT(*) FROM likes l WHERE l.liked_id=u.id) AS likes_received
        FROM users u
        ORDER BY datetime(u.created_at) DESC, u.id DESC
    ''')
    out = [dict(row) for row in cur.fetchall()]
    c.close()
    return out


@app.post('/api/register')
def register(data: Register):
    if data.age < 18:
        raise HTTPException(400, 'LoveBirdies is for adults aged 18+ only')
    if len(data.password) < 8:
        raise HTTPException(400, 'Password must be at least 8 characters')

    c = conn()
    cur = c.cursor()
    try:
        cur.execute(
            '''INSERT INTO users(email,password_hash,name,age,location,handicap,gender,interested_in,looking_for,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (
                data.email.lower().strip(), hash_password(data.password), data.name.strip(),
                data.age, data.location.strip(), data.handicap, data.gender,
                data.interested_in, data.looking_for, datetime.utcnow().isoformat()
            ),
        )
        uid = cur.lastrowid
        token = secrets.token_urlsafe(32)
        cur.execute('INSERT INTO sessions VALUES(?,?,?)', (token, uid, datetime.utcnow().isoformat()))
        c.commit()
    except sqlite3.IntegrityError:
        c.close()
        raise HTTPException(409, 'An account with that email already exists')

    c.close()
    return {'token': token, 'user_id': uid}


@app.post('/api/login')
def login(data: Login):
    c = conn()
    cur = c.cursor()
    cur.execute('SELECT * FROM users WHERE email=?', (data.email.lower().strip(),))
    u = cur.fetchone()
    if not u or not verify_password(data.password, u['password_hash']):
        c.close()
        raise HTTPException(401, 'Incorrect email or password')

    token = secrets.token_urlsafe(32)
    cur.execute('INSERT INTO sessions VALUES(?,?,?)', (token, u['id'], datetime.utcnow().isoformat()))
    c.commit()
    c.close()
    return {'token': token, 'user_id': u['id']}


@app.get('/api/me')
def me(authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute('SELECT * FROM users WHERE id=?', (uid,))
    u = cur.fetchone()
    c.close()
    return public_user(u)


@app.put('/api/me')
def update_me(data: ProfileUpdate, authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    fields = []
    vals = []
    for k, v in data.model_dump(exclude_unset=True).items():
        fields.append(f'{k}=?')
        vals.append(v)
    if fields:
        vals.append(uid)
        c = conn()
        c.execute('UPDATE users SET ' + ','.join(fields) + ' WHERE id=?', vals)
        c.commit()
        c.close()
    return {'ok': True}


@app.get('/api/discover')
def discover(authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute(
        '''SELECT * FROM users
        WHERE id!=? AND id NOT IN (SELECT liked_id FROM likes WHERE liker_id=?)
        ORDER BY verified DESC,id DESC LIMIT 30''',
        (uid, uid),
    )
    out = [public_user(x) for x in cur.fetchall()]
    c.close()
    return out


@app.post('/api/like/{other_id}')
def like(other_id: int, authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    if uid == other_id:
        raise HTTPException(400, 'Cannot like yourself')
    c = conn()
    cur = c.cursor()
    cur.execute('INSERT OR IGNORE INTO likes VALUES(?,?,?)', (uid, other_id, datetime.utcnow().isoformat()))
    cur.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?', (other_id, uid))
    matched = cur.fetchone() is not None
    c.commit()
    c.close()
    return {'matched': matched}


@app.get('/api/matches')
def matches(authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute(
        '''SELECT u.* FROM users u
        JOIN likes a ON a.liked_id=u.id
        JOIN likes b ON b.liker_id=u.id AND b.liked_id=a.liker_id
        WHERE a.liker_id=? ORDER BY a.created_at DESC''',
        (uid,),
    )
    out = [public_user(x) for x in cur.fetchall()]
    c.close()
    return out


@app.get('/api/messages/{other_id}')
def get_messages(other_id: int, authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    c = conn()
    cur = c.cursor()
    cur.execute(
        '''SELECT m.*, s.name sender_name FROM messages m
        JOIN users s ON s.id=m.sender_id
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY m.id''',
        (uid, other_id, other_id, uid),
    )
    out = [dict(x) for x in cur.fetchall()]
    c.close()
    return out


@app.post('/api/messages')
def send_message(data: MessageIn, authorization: Optional[str] = Header(None)):
    uid = auth_user(authorization)
    body = data.body.strip()
    if not body:
        raise HTTPException(400, 'Message cannot be empty')

    c = conn()
    cur = c.cursor()
    cur.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?', (uid, data.receiver_id))
    a = cur.fetchone()
    cur.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?', (data.receiver_id, uid))
    b = cur.fetchone()
    if not (a and b):
        c.close()
        raise HTTPException(403, 'You can only message a match')

    cur.execute(
        'INSERT INTO messages(sender_id,receiver_id,body,created_at) VALUES(?,?,?,?)',
        (uid, data.receiver_id, body, datetime.utcnow().isoformat()),
    )
    c.commit()
    c.close()
    return {'ok': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))
