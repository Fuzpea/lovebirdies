# LoveBirdies Full MVP

A working local MVP for a dating app aimed at golfers.

## Features
- Account registration and login
- Password hashing (PBKDF2)
- SQLite persistence
- Editable golfer profiles
- Discovery feed
- Likes and mutual matches
- Private messages between matches
- Responsive web UI
- Seed demo profiles

## Run on your Mac
Open Terminal in this folder, then:

```bash
python3 -m uvicorn main:app --reload
```

Open:

http://127.0.0.1:8000

If `uvicorn` is missing:

```bash
python3 -m pip install fastapi uvicorn sqlalchemy
```

## Demo account
- aoife@example.com
- Demo123!

You can also create a new account.

## Testing a match
A message conversation is only allowed after a mutual match. While logged in, you can open the browser developer console and run:

```js
demoMatch(1)
```

This creates a mutual match with demo user ID 1 for testing.

## Production upgrades still needed
This MVP is suitable for product testing, not public launch. Before production:
- Hosted database and managed auth
- Email verification / password reset
- Photo uploads to object storage
- Age/identity verification
- Robust report/block/moderation workflow
- Location/privacy controls
- Matching preference enforcement
- Rate limiting and abuse prevention
- Content moderation
- GDPR/privacy policy and deletion/export workflows
- HTTPS, security headers and CSRF strategy
- Payments/subscriptions
- Admin dashboard
- Automated tests and deployment pipeline

## Public deployment
This version is prepared for Railway deployment. See `DEPLOY_ONLINE.md`.

The database location can be controlled with `DATA_DIR`; set it to the mount path of a persistent Railway Volume (recommended: `/data`).
