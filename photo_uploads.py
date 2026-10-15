from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
import os, secrets, sqlite3, io
from datetime import datetime, timedelta
from PIL import Image, UnidentifiedImageError, ImageOps
from golf_features import router as golf_router

router = APIRouter()
router.include_router(golf_router)
BASE = os.path.dirname(__file__)
DATA_DIR = os.environ.get('DATA_DIR', BASE)
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
DB = os.path.join(DATA_DIR, 'lovebirdies.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
MAX_BYTES = 5 * 1024 * 1024

def user_from_token(authorization: Optional[str]):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401, 'Please log in')
    token = authorization[7:]; c = sqlite3.connect(DB); row = c.execute('SELECT user_id,created_at FROM sessions WHERE token=?', (token,)).fetchone(); c.close()
    if not row: raise HTTPException(401, 'Session expired')
    try:
        if datetime.fromisoformat(row[1]) + timedelta(hours=max(1,int(os.environ.get('SESSION_HOURS','168')))) <= datetime.utcnow():
            raise HTTPException(401, 'Session expired')
    except (ValueError, TypeError):
        raise HTTPException(401, 'Session expired')
    return row[0]

@router.get('/clubs')
def clubs_page(): return FileResponse(os.path.join(BASE,'static','clubs.html'))

@router.post('/api/me/photo')
async def upload_profile_photo(request: Request, authorization: Optional[str] = Header(None)):
    uid = user_from_token(authorization); content_type = request.headers.get('content-type', '').split(';', 1)[0].lower()
    if content_type not in ALLOWED: raise HTTPException(415, 'Please upload a JPG, PNG or WebP image')
    if request.headers.get('content-length') and int(request.headers['content-length']) > MAX_BYTES: raise HTTPException(413, 'Photo must be 5 MB or smaller')
    body = await request.body()
    if not body: raise HTTPException(400, 'No image was uploaded')
    if len(body) > MAX_BYTES: raise HTTPException(413, 'Photo must be 5 MB or smaller')
    try:
        img = Image.open(io.BytesIO(body))
        img.verify()
        if img.format != {'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}[content_type]:
            raise ValueError('Image type mismatch')
    except (UnidentifiedImageError, ValueError, OSError):
        raise HTTPException(415, 'Invalid image file')
    try:
        img = Image.open(io.BytesIO(body))
        img = ImageOps.exif_transpose(img)
        if img.width * img.height > 25_000_000: raise ValueError('Image too large')
        img.thumbnail((2048, 2048))
        if content_type == 'image/jpeg':
            img = img.convert('RGB')
        output = io.BytesIO()
        img.save(output, format={'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}[content_type])
        body = output.getvalue()
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(415, 'Invalid or oversized image')
    filename = f'user-{uid}-{secrets.token_hex(8)}{ALLOWED[content_type]}'; path = os.path.join(UPLOAD_DIR, filename)
    with open(path, 'wb') as f: f.write(body)
    photo_url = f'/uploads/{filename}'; c = sqlite3.connect(DB); old = c.execute('SELECT photo FROM users WHERE id=?', (uid,)).fetchone(); c.execute('UPDATE users SET photo=? WHERE id=?', (photo_url, uid)); c.commit(); c.close()
    if old and old[0] and old[0].startswith('/uploads/'):
        old_path = os.path.join(UPLOAD_DIR, os.path.basename(old[0]))
        if old_path != path and os.path.exists(old_path):
            try: os.remove(old_path)
            except OSError: pass
    return {'photo': photo_url}

@router.get('/uploads/{filename}')
def uploaded_photo(filename: str, authorization: Optional[str] = Header(None)):
    """Only the owner or a non-blocked, discoverable member may retrieve a profile photo."""
    uid = user_from_token(authorization)
    safe = os.path.basename(filename)
    if safe != filename: raise HTTPException(404)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    owner = c.execute('SELECT id,age,gender,interested_in,photo,min_age,max_age FROM users WHERE photo=?', ('/uploads/'+safe,)).fetchone()
    viewer = c.execute('SELECT id,age,gender,interested_in,min_age,max_age FROM users WHERE id=?', (uid,)).fetchone()
    if not owner or not viewer:
        c.close(); raise HTTPException(404, 'Photo not found')
    if owner['id'] != uid:
        blocked = c.execute('SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)', (uid,owner['id'],owner['id'],uid)).fetchone()
        mutual = c.execute('SELECT 1 FROM likes a JOIN likes b ON b.liker_id=a.liked_id AND b.liked_id=a.liker_id WHERE a.liker_id=? AND a.liked_id=?', (uid,owner['id'])).fetchone()
        def interested(wanted, gender):
            return not wanted or wanted == 'Everyone' or (wanted == 'Men' and gender == 'Man') or (wanted == 'Women' and gender == 'Woman') or wanted == gender
        compatible = (owner['age'] >= (viewer['min_age'] or 18) and owner['age'] <= (viewer['max_age'] or 99) and viewer['age'] >= (owner['min_age'] or 18) and viewer['age'] <= (owner['max_age'] or 99) and interested(viewer['interested_in'],owner['gender']) and interested(owner['interested_in'],viewer['gender']))
        if blocked or not (mutual or compatible):
            c.close(); raise HTTPException(404, 'Photo not found')
    c.close()
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path): raise HTTPException(404, 'Photo not found')
    response = FileResponse(path, headers={'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff'})
    return response
