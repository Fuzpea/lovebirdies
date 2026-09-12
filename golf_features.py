from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3, os, secrets, hashlib
from datetime import datetime

router=APIRouter(); BASE=os.path.dirname(__file__); DATA_DIR=os.environ.get('DATA_DIR',BASE); DB=os.path.join(DATA_DIR,'lovebirdies.db')
def conn(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def now(): return datetime.utcnow().isoformat()
def hp(p,s=None):
 s=s or secrets.token_hex(16); d=hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),180000).hex(); return f'{s}${d}'
def vp(p,x):
 try: s,d=x.split('$',1); return secrets.compare_digest(hp(p,s).split('$',1)[1],d)
 except: return False
def user(a):
 if not a or not a.startswith('Bearer '): raise HTTPException(401,'Please log in')
 c=conn(); r=c.execute('SELECT user_id FROM sessions WHERE token=?',(a[7:],)).fetchone(); c.close()
 if not r: raise HTTPException(401,'Session expired')
 return r['user_id']
def club(a):
 if not a or not a.startswith('Bearer '): raise HTTPException(401,'Club login required')
 c=conn(); r=c.execute('SELECT club_id FROM club_sessions WHERE token=?',(a[7:],)).fetchone(); c.close()
 if not r: raise HTTPException(401,'Club session expired')
 return r['club_id']
def ensure_col(c,table,name,definition):
 cols=[r['name'] for r in c.execute(f'PRAGMA table_info({table})').fetchall()]
 if name not in cols: c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
def init():
 c=conn(); c.executescript('''
 CREATE TABLE IF NOT EXISTS clubs(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,location TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,website TEXT DEFAULT '',description TEXT DEFAULT '',logo TEXT DEFAULT '',verified INTEGER DEFAULT 0,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS club_sessions(token TEXT PRIMARY KEY,club_id INTEGER NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS golf_posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,kind TEXT NOT NULL,venue TEXT NOT NULL,event_date TEXT NOT NULL,event_time TEXT NOT NULL,holes TEXT DEFAULT '',style TEXT DEFAULT 'Social',notes TEXT DEFAULT '',capacity INTEGER DEFAULT 2,status TEXT DEFAULT 'open',created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS golf_interest(id INTEGER PRIMARY KEY AUTOINCREMENT,post_id INTEGER NOT NULL,user_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(post_id,user_id));
 CREATE TABLE IF NOT EXISTS club_events(id INTEGER PRIMARY KEY AUTOINCREMENT,club_id INTEGER NOT NULL,title TEXT NOT NULL,event_date TEXT NOT NULL,event_time TEXT NOT NULL,format TEXT DEFAULT '9-hole social golf',description TEXT DEFAULT '',price REAL DEFAULT 0,capacity INTEGER DEFAULT 24,status TEXT DEFAULT 'published',created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS event_bookings(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT DEFAULT 'going',created_at TEXT NOT NULL,UNIQUE(event_id,user_id));
 ''')
 for n,d in [('hero_image',"TEXT DEFAULT ''"),('contact_name',"TEXT DEFAULT ''"),('tagline',"TEXT DEFAULT ''")]: ensure_col(c,'clubs',n,d)
 c.commit(); c.close()
init()
class PostIn(BaseModel): kind:str; venue:str; event_date:str; event_time:str; holes:str=''; style:str='Social'; notes:str=''; capacity:int=2
class ClubRegister(BaseModel): name:str; location:str; email:str; password:str; website:str=''; description:str=''
class ClubLogin(BaseModel): email:str; password:str
class ClubUpdate(BaseModel): name:Optional[str]=None; location:Optional[str]=None; website:Optional[str]=None; description:Optional[str]=None; logo:Optional[str]=None; hero_image:Optional[str]=None; contact_name:Optional[str]=None; tagline:Optional[str]=None
class EventIn(BaseModel): title:str='LoveBirdies Singles Golf Night'; event_date:str; event_time:str; format:str='9-hole social golf'; description:str=''; price:float=0; capacity:int=24
@router.get('/api/golf/feed')
def feed(authorization:Optional[str]=Header(None)):
 uid=user(authorization); c=conn(); posts=c.execute('''SELECT p.*,u.name host_name,u.handicap host_handicap,u.photo host_photo,(SELECT COUNT(*) FROM golf_interest i WHERE i.post_id=p.id) interested,EXISTS(SELECT 1 FROM golf_interest i WHERE i.post_id=p.id AND i.user_id=?) mine FROM golf_posts p JOIN users u ON u.id=p.user_id WHERE p.status='open' AND p.event_date>=date('now') ORDER BY p.event_date,p.event_time''',(uid,)).fetchall(); events=c.execute('''SELECT e.*,c.name club_name,c.location club_location,c.verified club_verified,c.logo club_logo,c.tagline club_tagline,(SELECT COUNT(*) FROM event_bookings b WHERE b.event_id=e.id AND b.status='going') booked,EXISTS(SELECT 1 FROM event_bookings b WHERE b.event_id=e.id AND b.user_id=? AND b.status='going') mine FROM club_events e JOIN clubs c ON c.id=e.club_id WHERE e.status='published' AND e.event_date>=date('now') ORDER BY e.event_date,e.event_time''',(uid,)).fetchall(); c.close(); return {'posts':[dict(x) for x in posts],'events':[dict(x) for x in events]}
@router.post('/api/golf/posts')
def create_post(d:PostIn,authorization:Optional[str]=Header(None)):
 uid=user(authorization)
 if d.kind not in ('round','19th'): raise HTTPException(400,'Invalid golf activity')
 if not d.venue.strip() or not d.event_date or not d.event_time: raise HTTPException(400,'Venue, date and time are required')
 c=conn(); cur=c.execute('INSERT INTO golf_posts(user_id,kind,venue,event_date,event_time,holes,style,notes,capacity,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,d.kind,d.venue.strip(),d.event_date,d.event_time,d.holes,d.style,d.notes.strip(),max(2,min(d.capacity,8)),'open',now())); c.commit(); i=cur.lastrowid; c.close(); return {'ok':True,'id':i}
@router.post('/api/golf/posts/{post_id}/interest')
def interest(post_id:int,authorization:Optional[str]=Header(None)):
 uid=user(authorization); c=conn(); p=c.execute('SELECT user_id FROM golf_posts WHERE id=? AND status="open"',(post_id,)).fetchone()
 if not p: c.close(); raise HTTPException(404,'Activity not found')
 if p['user_id']==uid: c.close(); raise HTTPException(400,'This is your activity')
 c.execute('INSERT OR IGNORE INTO golf_interest(post_id,user_id,created_at) VALUES(?,?,?)',(post_id,uid,now())); c.commit(); c.close(); return {'ok':True}
@router.delete('/api/golf/posts/{post_id}/interest')
def uninterest(post_id:int,authorization:Optional[str]=Header(None)):
 uid=user(authorization); c=conn(); c.execute('DELETE FROM golf_interest WHERE post_id=? AND user_id=?',(post_id,uid)); c.commit(); c.close(); return {'ok':True}
@router.post('/api/golf/events/{event_id}/book')
def book(event_id:int,authorization:Optional[str]=Header(None)):
 uid=user(authorization); c=conn(); e=c.execute('SELECT capacity,(SELECT COUNT(*) FROM event_bookings WHERE event_id=? AND status="going") booked FROM club_events WHERE id=? AND status="published"',(event_id,event_id)).fetchone()
 if not e: c.close(); raise HTTPException(404,'Event not found')
 if e['booked']>=e['capacity']: c.close(); raise HTTPException(409,'This event is full')
 c.execute('INSERT INTO event_bookings(event_id,user_id,status,created_at) VALUES(?,?,?,?) ON CONFLICT(event_id,user_id) DO UPDATE SET status="going"',(event_id,uid,'going',now())); c.commit(); c.close(); return {'ok':True}
@router.delete('/api/golf/events/{event_id}/book')
def cancel_book(event_id:int,authorization:Optional[str]=Header(None)):
 uid=user(authorization); c=conn(); c.execute('UPDATE event_bookings SET status="cancelled" WHERE event_id=? AND user_id=?',(event_id,uid)); c.commit(); c.close(); return {'ok':True}
@router.post('/api/clubs/register')
def club_register(d:ClubRegister):
 if len(d.password)<8: raise HTTPException(400,'Password must be at least 8 characters')
 c=conn()
 try:
  cur=c.execute('INSERT INTO clubs(name,location,email,password_hash,website,description,created_at) VALUES(?,?,?,?,?,?,?)',(d.name.strip(),d.location.strip(),d.email.lower().strip(),hp(d.password),d.website.strip(),d.description.strip(),now())); cid=cur.lastrowid; t=secrets.token_urlsafe(32); c.execute('INSERT INTO club_sessions VALUES(?,?,?)',(t,cid,now())); c.commit()
 except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'A club account with that email already exists')
 c.close(); return {'token':t,'club_id':cid}
@router.post('/api/clubs/login')
def club_login(d:ClubLogin):
 c=conn(); x=c.execute('SELECT * FROM clubs WHERE email=?',(d.email.lower().strip(),)).fetchone()
 if not x or not vp(d.password,x['password_hash']): c.close(); raise HTTPException(401,'Incorrect email or password')
 t=secrets.token_urlsafe(32); c.execute('INSERT INTO club_sessions VALUES(?,?,?)',(t,x['id'],now())); c.commit(); c.close(); return {'token':t,'club_id':x['id']}
@router.get('/api/clubs/me')
def club_me(authorization:Optional[str]=Header(None)):
 cid=club(authorization); c=conn(); x=c.execute('SELECT id,name,location,email,website,description,logo,hero_image,contact_name,tagline,verified FROM clubs WHERE id=?',(cid,)).fetchone(); c.close(); return dict(x)
@router.put('/api/clubs/me')
def club_update(d:ClubUpdate,authorization:Optional[str]=Header(None)):
 cid=club(authorization); data=d.model_dump(exclude_unset=True); fields=[]; vals=[]
 for k,v in data.items(): fields.append(k+'=?'); vals.append(v.strip() if isinstance(v,str) else v)
 if fields: vals.append(cid); c=conn(); c.execute('UPDATE clubs SET '+','.join(fields)+' WHERE id=?',vals); c.commit(); c.close()
 return {'ok':True}
@router.get('/api/clubs/events')
def club_events(authorization:Optional[str]=Header(None)):
 cid=club(authorization); c=conn(); rows=c.execute('''SELECT e.*,(SELECT COUNT(*) FROM event_bookings b WHERE b.event_id=e.id AND b.status='going') booked FROM club_events e WHERE club_id=? ORDER BY event_date DESC,event_time''',(cid,)).fetchall(); c.close(); return [dict(x) for x in rows]
@router.get('/api/clubs/events/{event_id}/attendees')
def event_attendees(event_id:int,authorization:Optional[str]=Header(None)):
 cid=club(authorization); c=conn(); own=c.execute('SELECT 1 FROM club_events WHERE id=? AND club_id=?',(event_id,cid)).fetchone()
 if not own: c.close(); raise HTTPException(404,'Event not found')
 rows=c.execute('''SELECT u.id,u.name,u.email,u.age,u.location,u.handicap,b.created_at booked_at FROM event_bookings b JOIN users u ON u.id=b.user_id WHERE b.event_id=? AND b.status='going' ORDER BY b.created_at''',(event_id,)).fetchall(); c.close(); return [dict(x) for x in rows]
@router.post('/api/clubs/events')
def create_event(d:EventIn,authorization:Optional[str]=Header(None)):
 cid=club(authorization); c=conn(); cur=c.execute('INSERT INTO club_events(club_id,title,event_date,event_time,format,description,price,capacity,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,d.title.strip(),d.event_date,d.event_time,d.format.strip(),d.description.strip(),max(0,d.price),max(4,min(d.capacity,200)),'published',now())); c.commit(); i=cur.lastrowid; c.close(); return {'ok':True,'id':i}
@router.put('/api/clubs/events/{event_id}/cancel')
def cancel_event(event_id:int,authorization:Optional[str]=Header(None)):
 cid=club(authorization); c=conn(); c.execute('UPDATE club_events SET status="cancelled" WHERE id=? AND club_id=?',(event_id,cid)); c.commit(); c.close(); return {'ok':True}
@router.get('/api/clubs/public/{club_id}')
def public_club(club_id:int):
 c=conn(); x=c.execute('SELECT id,name,location,website,description,logo,hero_image,contact_name,tagline,verified,created_at FROM clubs WHERE id=?',(club_id,)).fetchone()
 if not x: c.close(); raise HTTPException(404,'Club not found')
 upcoming=c.execute("SELECT COUNT(*) n FROM club_events WHERE club_id=? AND status='published' AND event_date>=date('now')",(club_id,)).fetchone()['n']; past=c.execute("SELECT COUNT(*) n FROM club_events WHERE club_id=? AND event_date<date('now')",(club_id,)).fetchone()['n']; attendees=c.execute("SELECT COUNT(*) n FROM event_bookings b JOIN club_events e ON e.id=b.event_id WHERE e.club_id=? AND b.status='going'",(club_id,)).fetchone()['n']; out=dict(x); out.update({'upcoming_events':upcoming,'past_events':past,'total_bookings':attendees}); c.close(); return out
@router.get('/api/clubs/public/{club_id}/events')
def public_club_events(club_id:int):
 c=conn(); rows=c.execute('''SELECT e.*,(SELECT COUNT(*) FROM event_bookings b WHERE b.event_id=e.id AND b.status='going') booked FROM club_events e WHERE e.club_id=? ORDER BY e.event_date DESC,e.event_time''',(club_id,)).fetchall(); c.close(); return [dict(x) for x in rows]
