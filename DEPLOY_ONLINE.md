# Put LoveBirdies online with Railway

This package is configured for Railway.

## 1. Put the project on GitHub
The project files should be in the `lovebirdies` repository.

## 2. Create a Railway project
- Sign in to Railway.
- Choose **New Project → Deploy from GitHub repo**.
- Select the `lovebirdies` repository.
- Railway should detect the Python app automatically.

## 3. Add persistent storage
LoveBirdies currently uses SQLite. Add a Railway Volume and mount it at:

`/data`

Then add this service variable:

`DATA_DIR=/data`

This keeps accounts, likes, matches and messages after restarts/redeploys.

## 4. Generate the public URL
In the Railway service settings, open **Networking** and generate a domain.
Railway will give you a public `*.up.railway.app` address.

## 5. Test
Open:

`https://YOUR-DOMAIN/health`

You should see:

`{"status":"ok"}`

Then open the root URL and register a new LoveBirdies account.

## Demo account
Email: `aoife@example.com`
Password: `Demo123!`

## Before inviting real users
The current MVP is suitable for controlled testing, not a production dating service. Before a public launch add at minimum:
- HTTPS-only production configuration (the host provides HTTPS)
- email verification and password reset
- stronger session management / expiry
- profile-photo upload storage
- reporting and blocking
- moderation/admin controls
- privacy policy and terms
- deletion/export of user data
- abuse/rate-limit controls
- database backups
- GDPR/data-retention review

## Custom domain
Once the Railway URL works, add your LoveBirdies domain in Railway's custom-domain settings and update the DNS records at your domain registrar.
