from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3, hashlib, secrets, os, math
from datetime import datetime
from photo_uploads import router as photo_router
from email_notifications import notify_like, notify_match, notify_message

BASE=os.path.dirname(__file__)
DATA_DIR=os.environ.get('DATA_DIR',BASE)
os.makedirs(DATA_DIR,exist_ok=True)
DB=os.path.join(DATA_DIR,'lovebirdies.db')
UPLOAD_DIR=os.path.join(DATA_DIR,'uploads')
app=FastAPI(title='LoveBirdies MVP')
app.mount('/static',StaticFiles(directory=os.path.join(BASE,'static')),name='static')
app.include_router(photo_router)

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def hash_password(password,salt=None):
 salt=salt or secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180_000).hex(); return f'{salt}${digest}'

def verify_password(password,stored):
 salt,digest=stored.split('$',1); return secrets.compare_digest(hash_password(password,salt).split('$',1)[1],digest)

def add_column(c,name,definition):
 cols=[r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()]
 if name not in cols: c.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')

def init_db():
 c=conn(); c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,name TEXT NOT NULL,age INTEGER NOT NULL,location TEXT NOT NULL,handicap REAL,gender TEXT DEFAULT '',interested_in TEXT DEFAULT '',looking_for TEXT DEFAULT 'Dating and seeing where it goes',bio TEXT DEFAULT '',golf_style TEXT DEFAULT 'Social golfer',home_club TEXT DEFAULT '',photo TEXT DEFAULT '',verified INTEGER DEFAULT 0,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS admin_sessions(token TEXT PRIMARY KEY,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS likes(liker_id INTEGER NOT NULL,liked_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(liker_id,liked_id)); CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_id INTEGER NOT NULL,receiver_id INTEGER NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS blocks(blocker_id INTEGER NOT NULL,blocked_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(blocker_id,blocked_id)); CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,reporter_id INTEGER NOT NULL,reported_id INTEGER NOT NULL,reason TEXT NOT NULL,details TEXT DEFAULT '',status TEXT DEFAULT 'open',created_at TEXT NOT NULL);''')
 for n,d in [('min_age','INTEGER DEFAULT 18'),('max_age','INTEGER DEFAULT 80'),('search_radius','INTEGER DEFAULT 50'),('onboarding_complete','INTEGER DEFAULT 0'),('latitude','REAL'),('longitude','REAL')]: add_column(c,n,d)
 c.commit(); c.close()

def remove_old_demo_accounts():
 demos=('aoife@example.com','david@example.com','sarah@example.com','mark@example.com'); c=conn(); q=','.join('?'*len(demos)); ids=[r['id'] for r in c.execute(f'SELECT id FROM users WHERE email IN ({q})',demos).fetchall()]
 if ids:
  iq=','.join('?'*len(ids)); c.execute(f'DELETE FROM messages WHERE sender_id IN ({iq}) OR receiver_id IN ({iq})',ids+ids); c.execute(f'DELETE FROM likes WHERE liker_id IN ({iq}) OR liked_id IN ({iq})',ids+ids); c.execute(f'DELETE FROM blocks WHERE blocker_id IN ({iq}) OR blocked_id IN ({iq})',ids+ids); c.execute(f'DELETE FROM reports WHERE reporter_id IN ({iq}) OR reported_id IN ({iq})',ids+ids); c.execute(f'DELETE FROM sessions WHERE user_id IN ({iq})',ids); c.execute(f'DELETE FROM users WHERE id IN ({iq})',ids); c.commit()
 c.close()

init_db(); remove_old_demo_accounts()

class Register(BaseModel):
 email:str; password:str; name:str; age:int; location:str; handicap:Optional[float]=None; gender:str=''; interested_in:str=''; looking_for:str='Dating and seeing where it goes'
class Login(BaseModel): email:str; password:str
class AdminLogin(BaseModel): email:str; password:str
class ProfileUpdate(BaseModel):
 name:Optional[str]=None; age:Optional[int]=None; location:Optional[str]=None; handicap:Optional[float]=None; gender:Optional[str]=None; interested_in:Optional[str]=None; looking_for:Optional[str]=None; bio:Optional[str]=None; golf_style:Optional[str]=None; home_club:Optional[str]=None; photo:Optional[str]=None; min_age:Optional[int]=None; max_age:Optional[int]=None; search_radius:Optional[int]=None; onboarding_complete:Optional[int]=None; latitude:Optional[float]=None; longitude:Optional[float]=None
class MessageIn(BaseModel): receiver_id:int; body:str
class ReportIn(BaseModel): reported_id:int; reason:str; details:str=''
class DeleteAccountIn(BaseModel): password:str
class ReportStatusIn(BaseModel): status:str

def auth_user(a):
 if not a or not a.startswith('Bearer '): raise HTTPException(401,'Please log in')
 c=conn(); r=c.execute('SELECT user_id FROM sessions WHERE token=?',(a[7:],)).fetchone(); c.close()
 if not r: raise HTTPException(401,'Session expired')
 return r['user_id']

def auth_admin(a):
 if not a or not a.startswith('Bearer '): raise HTTPException(401,'Admin login required')
 c=conn(); r=c.execute('SELECT token FROM admin_sessions WHERE token=?',(a[7:],)).fetchone(); c.close()
 if not r: raise HTTPException(401,'Admin session expired')

def public_user(r,distance=None):
 out={k:r[k] for k in ['id','name','age','location','handicap','gender','interested_in','looking_for','bio','golf_style','home_club','photo','verified','min_age','max_age','search_radius','onboarding_complete']}
 if distance is not None: out['distance_km']=round(distance)
 return out

def self_user(r):
 out=public_user(r); out['has_location_coordinates']=r['latitude'] is not None and r['longitude'] is not None; return out

def distance_km(a,b,c,d):
 R=6371.0; p1=math.radians(a); p2=math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def blocked(c,a,b):
 return c.execute('SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)',(a,b,b,a)).fetchone() is not None

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/')
def home(): return FileResponse(os.path.join(BASE,'static','index.html'))

@app.get('/join')
def join_page(): return FileResponse(os.path.join(BASE,'static','join.html'))

@app.get('/admin')
def admin_page(): return FileResponse(os.path.join(BASE,'static','admin.html'))

@app.post('/api/admin/login')
def admin_login(d:AdminLogin):
 e=os.environ.get('ADMIN_EMAIL','').strip().lower(); p=os.environ.get('ADMIN_PASSWORD','')
 if not e or not p: raise HTTPException(503,'Admin access has not been configured')
 if not(secrets.compare_digest(d.email.strip().lower(),e) and secrets.compare_digest(d.password,p)): raise HTTPException(401,'Incorrect admin email or password')
 t=secrets.token_urlsafe(40); c=conn(); c.execute('INSERT INTO admin_sessions VALUES(?,?)',(t,datetime.utcnow().isoformat())); c.commit(); c.close(); return {'token':t}

@app.get('/api/admin/stats')
def admin_stats(authorization:Optional[str]=Header(None)):
 auth_admin(authorization); c=conn(); u=c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']; l=c.execute('SELECT COUNT(*) n FROM likes').fetchone()['n']; m=c.execute('SELECT COUNT(*) n FROM likes a JOIN likes b ON a.liker_id=b.liked_id AND a.liked_id=b.liker_id WHERE a.liker_id<a.liked_id').fetchone()['n']; x=c.execute('SELECT COUNT(*) n FROM messages').fetchone()['n']; r=c.execute("SELECT COUNT(*) n FROM reports WHERE status='open'").fetchone()['n']; c.close(); return {'users':u,'likes':l,'matches':m,'messages':x,'reports':r}

@app.get('/api/admin/users')
def admin_users(authorization:Optional[str]=Header(None)):
 auth_admin(authorization); c=conn(); rows=c.execute('''SELECT u.id,u.name,u.email,u.age,u.location,u.handicap,u.gender,u.interested_in,u.looking_for,u.golf_style,u.home_club,u.verified,u.created_at,(SELECT COUNT(*) FROM likes l WHERE l.liker_id=u.id) likes_sent,(SELECT COUNT(*) FROM likes l WHERE l.liked_id=u.id) likes_received FROM users u ORDER BY datetime(u.created_at) DESC,u.id DESC''').fetchall(); out=[dict(r) for r in rows]; c.close(); return out

@app.get('/api/admin/reports')
def admin_reports(authorization:Optional[str]=Header(None)):
 auth_admin(authorization); c=conn(); rows=c.execute('''SELECT r.id,r.reason,r.details,r.status,r.created_at,reporter.name reporter_name,reporter.email reporter_email,reported.name reported_name,reported.email reported_email FROM reports r JOIN users reporter ON reporter.id=r.reporter_id JOIN users reported ON reported.id=r.reported_id ORDER BY CASE WHEN r.status='open' THEN 0 ELSE 1 END,r.id DESC''').fetchall(); out=[dict(x) for x in rows]; c.close(); return out

@app.put('/api/admin/reports/{report_id}')
def admin_report_status(report_id:int,d:ReportStatusIn,authorization:Optional[str]=Header(None)):
 auth_admin(authorization)
 if d.status not in ('open','reviewed','closed'): raise HTTPException(400,'Invalid report status')
 c=conn(); c.execute('UPDATE reports SET status=? WHERE id=?',(d.status,report_id)); c.commit(); c.close(); return {'ok':True}

@app.post('/api/register')
def register(d:Register):
 if d.age<18: raise HTTPException(400,'LoveBirdies is for adults aged 18+ only')
 if len(d.password)<8: raise HTTPException(400,'Password must be at least 8 characters')
 c=conn()
 try:
  cur=c.execute('INSERT INTO users(email,password_hash,name,age,location,handicap,gender,interested_in,looking_for,created_at,min_age,max_age,search_radius,onboarding_complete) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(d.email.lower().strip(),hash_password(d.password),d.name.strip(),d.age,d.location.strip(),d.handicap,d.gender,d.interested_in,d.looking_for,datetime.utcnow().isoformat(),max(18,d.age-10),min(99,d.age+10),50,0)); uid=cur.lastrowid; t=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions VALUES(?,?,?)',(t,uid,datetime.utcnow().isoformat())); c.commit()
 except sqlite3.IntegrityError:
  c.close(); raise HTTPException(409,'An account with that email already exists')
 c.close(); return {'token':t,'user_id':uid}

@app.post('/api/login')
def login(d:Login):
 c=conn(); u=c.execute('SELECT * FROM users WHERE email=?',(d.email.lower().strip(),)).fetchone()
 if not u or not verify_password(d.password,u['password_hash']): c.close(); raise HTTPException(401,'Incorrect email or password')
 t=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions VALUES(?,?,?)',(t,u['id'],datetime.utcnow().isoformat())); c.commit(); c.close(); return {'token':t,'user_id':u['id']}

@app.get('/api/me')
def me(authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); c=conn(); u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return self_user(u)

@app.put('/api/me')
def update_me(d:ProfileUpdate,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); data=d.model_dump(exclude_unset=True)
 if 'min_age' in data and data['min_age'] is not None and not 18<=data['min_age']<=99: raise HTTPException(400,'Minimum age must be between 18 and 99')
 if 'max_age' in data and data['max_age'] is not None and not 18<=data['max_age']<=99: raise HTTPException(400,'Maximum age must be between 18 and 99')
 if data.get('latitude') is not None and not -90<=data['latitude']<=90: raise HTTPException(400,'Invalid latitude')
 if data.get('longitude') is not None and not -180<=data['longitude']<=180: raise HTTPException(400,'Invalid longitude')
 fields=[]; vals=[]
 for k,v in data.items(): fields.append(f'{k}=?'); vals.append(v)
 if fields:
  vals.append(uid); c=conn(); c.execute('UPDATE users SET '+','.join(fields)+' WHERE id=?',vals); c.commit(); c.close()
 return {'ok':True}

@app.delete('/api/me')
def delete_me(d:DeleteAccountIn,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); c=conn(); u=c.execute('SELECT password_hash,photo FROM users WHERE id=?',(uid,)).fetchone()
 if not u or not verify_password(d.password,u['password_hash']): c.close(); raise HTTPException(401,'Incorrect password')
 photo=u['photo']; c.execute('DELETE FROM messages WHERE sender_id=? OR receiver_id=?',(uid,uid)); c.execute('DELETE FROM likes WHERE liker_id=? OR liked_id=?',(uid,uid)); c.execute('DELETE FROM blocks WHERE blocker_id=? OR blocked_id=?',(uid,uid)); c.execute('DELETE FROM reports WHERE reporter_id=? OR reported_id=?',(uid,uid)); c.execute('DELETE FROM sessions WHERE user_id=?',(uid,)); c.execute('DELETE FROM users WHERE id=?',(uid,)); c.commit(); c.close()
 if photo and photo.startswith('/uploads/'):
  p=os.path.join(UPLOAD_DIR,os.path.basename(photo))
  if os.path.isfile(p):
   try: os.remove(p)
   except OSError: pass
 return {'ok':True}

def gender_matches(wanted,gender):
 if not wanted or wanted=='Everyone': return True
 return (wanted=='Men' and gender=='Man') or (wanted=='Women' and gender=='Woman') or wanted==gender

@app.get('/api/discover')
def discover(authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); c=conn(); viewer=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); rows=c.execute('''SELECT * FROM users WHERE id!=? AND id NOT IN (SELECT liked_id FROM likes WHERE liker_id=?) AND id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id=?) AND id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id=?) ORDER BY verified DESC,id DESC LIMIT 150''',(uid,uid,uid,uid)).fetchall(); out=[]
 for r in rows:
  if r['age']<(viewer['min_age'] or 18) or r['age']>(viewer['max_age'] or 99): continue
  if not gender_matches(viewer['interested_in'],r['gender']) or not gender_matches(r['interested_in'],viewer['gender']): continue
  dist=None
  if viewer['latitude'] is not None and viewer['longitude'] is not None and r['latitude'] is not None and r['longitude'] is not None:
   dist=distance_km(viewer['latitude'],viewer['longitude'],r['latitude'],r['longitude'])
   if dist>(viewer['search_radius'] or 50): continue
  out.append(public_user(r,dist))
  if len(out)>=30: break
 c.close(); return out

@app.post('/api/like/{other_id}')
def like(other_id:int,background_tasks:BackgroundTasks,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization)
 if uid==other_id: raise HTTPException(400,'Cannot like yourself')
 c=conn()
 if blocked(c,uid,other_id): c.close(); raise HTTPException(403,'This profile is unavailable')
 liker=c.execute('SELECT id,name,email FROM users WHERE id=?',(uid,)).fetchone(); liked=c.execute('SELECT id,name,email FROM users WHERE id=?',(other_id,)).fetchone()
 if not liked: c.close(); raise HTTPException(404,'Profile not found')
 cur=c.execute('INSERT OR IGNORE INTO likes VALUES(?,?,?)',(uid,other_id,datetime.utcnow().isoformat())); inserted=cur.rowcount==1
 matched=c.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?',(other_id,uid)).fetchone() is not None
 c.commit(); c.close()
 if inserted:
  if matched:
   background_tasks.add_task(notify_match,liked['email'],liked['name'],liker['name'])
   background_tasks.add_task(notify_match,liker['email'],liker['name'],liked['name'])
  else:
   background_tasks.add_task(notify_like,liked['email'],liked['name'],liker['name'])
 return {'matched':matched}

@app.post('/api/block/{other_id}')
def block_user(other_id:int,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization)
 if uid==other_id: raise HTTPException(400,'Cannot block yourself')
 c=conn(); c.execute('INSERT OR IGNORE INTO blocks VALUES(?,?,?)',(uid,other_id,datetime.utcnow().isoformat())); c.execute('DELETE FROM likes WHERE (liker_id=? AND liked_id=?) OR (liker_id=? AND liked_id=?)',(uid,other_id,other_id,uid)); c.commit(); c.close(); return {'ok':True}

@app.post('/api/report')
def report_user(d:ReportIn,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization)
 if uid==d.reported_id: raise HTTPException(400,'Cannot report yourself')
 reason=d.reason.strip(); details=d.details.strip()
 if not reason: raise HTTPException(400,'Please choose a reason')
 c=conn(); exists=c.execute('SELECT 1 FROM users WHERE id=?',(d.reported_id,)).fetchone()
 if not exists: c.close(); raise HTTPException(404,'Profile not found')
 c.execute('INSERT INTO reports(reporter_id,reported_id,reason,details,status,created_at) VALUES(?,?,?,?,?,?)',(uid,d.reported_id,reason,details,'open',datetime.utcnow().isoformat())); c.commit(); c.close(); return {'ok':True}

@app.get('/api/matches')
def matches(authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); c=conn(); rows=c.execute('''SELECT u.* FROM users u JOIN likes a ON a.liked_id=u.id JOIN likes b ON b.liker_id=u.id AND b.liked_id=a.liker_id WHERE a.liker_id=? AND NOT EXISTS(SELECT 1 FROM blocks x WHERE (x.blocker_id=? AND x.blocked_id=u.id) OR (x.blocker_id=u.id AND x.blocked_id=?)) ORDER BY a.created_at DESC''',(uid,uid,uid)).fetchall(); out=[public_user(r) for r in rows]; c.close(); return out

@app.get('/api/messages/{other_id}')
def get_messages(other_id:int,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); c=conn()
 if blocked(c,uid,other_id): c.close(); raise HTTPException(403,'This conversation is unavailable')
 rows=c.execute('SELECT m.*,s.name sender_name FROM messages m JOIN users s ON s.id=m.sender_id WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) ORDER BY m.id',(uid,other_id,other_id,uid)).fetchall(); out=[dict(r) for r in rows]; c.close(); return out

@app.post('/api/messages')
def send_message(d:MessageIn,background_tasks:BackgroundTasks,authorization:Optional[str]=Header(None)):
 uid=auth_user(authorization); body=d.body.strip()
 if not body: raise HTTPException(400,'Message cannot be empty')
 c=conn()
 if blocked(c,uid,d.receiver_id): c.close(); raise HTTPException(403,'This conversation is unavailable')
 a=c.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?',(uid,d.receiver_id)).fetchone(); b=c.execute('SELECT 1 FROM likes WHERE liker_id=? AND liked_id=?',(d.receiver_id,uid)).fetchone()
 if not(a and b): c.close(); raise HTTPException(403,'You can only message a match')
 sender=c.execute('SELECT name,email FROM users WHERE id=?',(uid,)).fetchone(); receiver=c.execute('SELECT name,email FROM users WHERE id=?',(d.receiver_id,)).fetchone()
 if not receiver: c.close(); raise HTTPException(404,'User not found')
 c.execute('INSERT INTO messages(sender_id,receiver_id,body,created_at) VALUES(?,?,?,?)',(uid,d.receiver_id,body,datetime.utcnow().isoformat())); c.commit(); c.close()
 background_tasks.add_task(notify_message,receiver['email'],receiver['name'],sender['name'],body)
 return {'ok':True}

if __name__=='__main__':
 import uvicorn; uvicorn.run(app,host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
