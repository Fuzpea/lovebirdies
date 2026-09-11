from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
import os, secrets, sqlite3

router = APIRouter()
BASE = os.path.dirname(__file__)
DATA_DIR = os.environ.get('DATA_DIR', BASE)
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
DB = os.path.join(DATA_DIR, 'lovebirdies.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
MAX_BYTES = 5 * 1024 * 1024


def user_from_token(authorization: Optional[str]):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Please log in')
    token = authorization[7:]
    c = sqlite3.connect(DB)
    row = c.execute('SELECT user_id FROM sessions WHERE token=?', (token,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(401, 'Session expired')
    return row[0]


@router.post('/api/me/photo')
async def upload_profile_photo(request: Request, authorization: Optional[str] = Header(None)):
    uid = user_from_token(authorization)
    content_type = request.headers.get('content-type', '').split(';', 1)[0].lower()
    if content_type not in ALLOWED:
        raise HTTPException(415, 'Please upload a JPG, PNG or WebP image')
    body = await request.body()
    if not body:
        raise HTTPException(400, 'No image was uploaded')
    if len(body) > MAX_BYTES:
        raise HTTPException(413, 'Photo must be 5 MB or smaller')

    filename = f'user-{uid}-{secrets.token_hex(8)}{ALLOWED[content_type]}'
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, 'wb') as f:
        f.write(body)

    photo_url = f'/uploads/{filename}'
    c = sqlite3.connect(DB)
    old = c.execute('SELECT photo FROM users WHERE id=?', (uid,)).fetchone()
    c.execute('UPDATE users SET photo=? WHERE id=?', (photo_url, uid))
    c.commit()
    c.close()

    if old and old[0] and old[0].startswith('/uploads/'):
        old_path = os.path.join(UPLOAD_DIR, os.path.basename(old[0]))
        if old_path != path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    return {'photo': photo_url}


@router.get('/uploads/{filename}')
def uploaded_photo(filename: str):
    safe = os.path.basename(filename)
    if safe != filename:
        raise HTTPException(404)
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, 'Photo not found')
    return FileResponse(path)
