# LoveBirdies staging security checklist

Do not connect this branch to the production database or upload directory.

## Staging setup (Railway)
1. Create a separate Railway service/environment from branch `security-hardening-prelaunch`.
2. Use an isolated persistent volume mounted at `/data`, and set `DATA_DIR=/data`.
3. Set a new `ADMIN_EMAIL` and a long random `ADMIN_PASSWORD` in staging variables.
4. Generate a unique TOTP secret locally with `python -c "import pyotp; print(pyotp.random_base32())"`. Set `ADMIN_TOTP_SECRET` in staging variables and enroll it in your authenticator app. Never commit the secret, print it in logs, or share it in chat.
5. Set `SESSION_HOURS=168`, `CLUB_SESSION_HOURS=168`, and `ADMIN_SESSION_HOURS=8`.
6. Give staging its own temporary Railway domain. Do not change GoDaddy DNS.
7. Ensure no production database or real user data is copied to staging.

## Acceptance checks
- Automated security workflow succeeds on the pull request.
- Create two test members. Upload an image; verify own and eligible-member views work.
- Unauthenticated photo URL request returns HTTP 401.
- Block member B from A; B's request for A's photo returns HTTP 404.
- Replace A's photo; old photo URL returns HTTP 404.
- Log out; previous token returns HTTP 401 for protected endpoints.
- Five failed member logins cause a temporary lockout. Verify recovery after expiry.
- Admin login without an authenticator code fails; valid password and code succeeds.
- Admin logout revokes the token.
- Verify club login/logout and session expiry.
- Verify normal registration, discover, matching, messaging, reporting and account deletion still work.
- Check browser console and Railway logs for unexpected errors, without exposing secrets.

## Production gate
Do not merge until staging tests pass, the Railway production volume and database backups are confirmed, and a restore is tested. The login limiter is per account, not per IP, and remains subject to distributed-abuse review. Review photo visibility policy and GDPR/age assurance before public launch.
