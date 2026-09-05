# LTMP — Luminary Telegram Management Panel

A private dashboard for managing **your own Telegram account** through Telethon.

## Local setup (Windows)

1. Install Python 3.9+ and make sure `python` works in Command Prompt.
2. Open `backend/data/backend.env`.
3. Set `API_ID` and `API_HASH` from Telegram's API Development Tools. Set `PHONE` if using phone login.
4. Run `backend/scripts/setup.bat` once.
5. Run `backend/scripts/start.bat`.
6. Open `http://localhost:3421`. The backend now serves the bundled frontend, so no second web server is required.

### Login
- `LOGIN_METHOD=phone`: enter your phone number and OTP in the dashboard.
- `LOGIN_METHOD=qr`: use Telegram → Settings → Devices → Link Desktop.

## Separate frontend / Render

If the frontend and backend are on different origins, the frontend automatically uses `https://backend.ltmp.qzz.io` for non-localhost deployments. You can override it by setting `window.LTMP_BACKEND_URL` in `frontend/backend-connection.js`. On Render, set `FRONTEND_ORIGINS` to the exact HTTPS origin of the frontend.

The Render backend uses `/var/data` for the Telegram session. Keep the persistent disk enabled so the session survives restarts.

## Security

- Never commit API credentials or `.session` files.
- If a real Telegram `.session` file or API credentials were previously exposed, revoke the Telegram session and rotate the credentials before production use.
- This is intended as a private, single-user control panel. Do not expose it publicly without adding an application authentication layer.
- API routes reject dialog operations when the Telegram client is not authorized.

## Health check

`GET /api/health` returns backend health information for local checks and Render.
