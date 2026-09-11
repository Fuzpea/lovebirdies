import json
import os
import urllib.request
import urllib.error
from html import escape

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'LoveBirdies <notifications@lovebirdies.ie>').strip()
APP_URL = os.environ.get('APP_URL', 'https://www.lovebirdies.ie').rstrip('/')


def email_enabled():
    return bool(RESEND_API_KEY and EMAIL_FROM)


def send_email(to_email: str, subject: str, heading: str, message: str, button_text: str = 'Open LoveBirdies') -> bool:
    if not email_enabled() or not to_email:
        return False
    html = f'''<!doctype html>
<html><body style="margin:0;background:#f7f8f5;font-family:Arial,sans-serif;color:#13201d">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 16px"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:white;border-radius:18px;padding:30px;border:1px solid #dce5df">
<tr><td style="font-size:22px;font-weight:700;color:#123f36">♥ LoveBirdies</td></tr>
<tr><td style="padding-top:24px;font-size:28px;font-weight:700">{escape(heading)}</td></tr>
<tr><td style="padding-top:14px;font-size:16px;line-height:1.55;color:#52615b">{escape(message)}</td></tr>
<tr><td style="padding-top:26px"><a href="{escape(APP_URL)}" style="display:inline-block;background:#123f36;color:white;text-decoration:none;padding:13px 22px;border-radius:999px;font-weight:700">{escape(button_text)}</a></td></tr>
<tr><td style="padding-top:28px;font-size:12px;color:#7a8782">You received this because you have a LoveBirdies account.</td></tr>
</table></td></tr></table></body></html>'''
    payload = json.dumps({
        'from': EMAIL_FROM,
        'to': [to_email],
        'subject': subject,
        'html': html,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=payload,
        headers={
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': 'LoveBirdies/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def notify_like(recipient_email: str, recipient_name: str, liker_name: str) -> bool:
    return send_email(
        recipient_email,
        'Someone liked you on LoveBirdies ❤️',
        'You received a like',
        f'{liker_name} liked your profile. Open LoveBirdies to see what happens next.',
        'See your profile',
    )


def notify_match(recipient_email: str, recipient_name: str, match_name: str) -> bool:
    return send_email(
        recipient_email,
        "It's a Birdie! You have a new match ❤️",
        "It's a match!",
        f'You and {match_name} liked each other. You can now start chatting on LoveBirdies.',
        'Open your match',
    )


def notify_message(recipient_email: str, recipient_name: str, sender_name: str, body: str) -> bool:
    preview = body.strip().replace('\n', ' ')
    if len(preview) > 120:
        preview = preview[:117] + '...'
    return send_email(
        recipient_email,
        f'New message from {sender_name} on LoveBirdies',
        f'{sender_name} sent you a message',
        f'“{preview}”',
        'Read message',
    )
