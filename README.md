# LTMP — Luminary Telegram Management Panel

## Deployment
This version is designed to deploy as **one Render web service**. The FastAPI backend serves the frontend from the same origin, so login/API/WebSocket requests do not depend on a separate `backend.ltmp.qzz.io` service.

### Render
1. Create a Render Blueprint from this repository/ZIP contents.
2. The included `render.yaml` creates one Python web service.
3. Set `API_ID` and `API_HASH` in Render Environment.
4. Set `PHONE` only if required by your login configuration.
5. Attach/use the persistent disk mounted at `/var/data`.
6. After deployment, open `/api/health`. It must return JSON with `status: ok`.
7. Then open the main site. The frontend automatically uses its own origin for API and WebSocket requests.

### Custom domain
Point your custom domain (for example `ltmp.qzz.io`) to the **single Render web service**, not to a separate backend hostname. Do not hard-code a backend subdomain in the frontend.

### Local
From the project root:
`python -m pip install -r backend/requirements.txt`
`python -m uvicorn backend.server:app --host 0.0.0.0 --port 3421`
Then open `http://127.0.0.1:3421`.

## Security
Do not commit `backend/data/backend.env`, Telegram API credentials, Telegram `.session` files, or 2FA secrets.
