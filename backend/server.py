"""
LTMP — Luminary Telegram Management Panel Backend
Reads config from environment variables or backend/data/backend.env
Start with: uvicorn server:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import json
import os
import sys
import qrcode
import io
import base64
from pathlib import Path
from contextlib import asynccontextmanager

# Load .env from data/backend.env (local dev). On Render, env vars are set in dashboard.
from dotenv import load_dotenv
_env_file = Path(__file__).parent / "data" / "backend.env"
if _env_file.exists():
    load_dotenv(_env_file)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeExpiredError,
    PhoneCodeInvalidError, FloodWaitError
)
from telethon.tl.functions.messages import ReadHistoryRequest

# ── Mock Telegram Client for Sandbox Mode ────────────────────────────────────
class MockUser:
    def __init__(self):
        self.first_name = "Demo"
        self.last_name = "User"
        self.username = "demouser"
        self.phone = "919999999999"
        self.id = 123456789

class MockDialog:
    def __init__(self, id, name, type_, unread=0, pinned=False, archived=False):
        self.id = id
        self.name = name
        self.type = type_
        self.is_channel = type_ == "channel"
        self.is_group = type_ == "group"
        self.unread_count = unread
        self.pinned = pinned
        self.archived = archived
        self.date = "2026-05-17 12:00:00"
        self.entity = self  # mock entity reference

class MockSentCode:
    def __init__(self):
        self.phone_code_hash = "mock_hash_12345"

class MockTelegramClient:
    def __init__(self, session, api_id, api_hash):
        self._connected = False
        self._authorized = False

    async def connect(self):
        self._connected = True

    def is_connected(self):
        return self._connected

    async def is_user_authorized(self):
        return self._authorized

    async def get_me(self):
        return MockUser()

    async def send_code_request(self, phone):
        return MockSentCode()

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        if code == "12345":
            self._authorized = True
        elif password == "password":
            self._authorized = True
        else:
            raise PhoneCodeInvalidError(request=None)

    async def log_out(self):
        self._authorized = False

    async def get_dialogs(self, limit=100):
        return [
            MockDialog(1001, "Tech Hackers Channel", "channel", unread=27),
            MockDialog(1002, "Global Tech Community", "group", unread=8),
            MockDialog(1003, "Spam Channel", "channel", unread=142),
            MockDialog(1004, "Developer Chat", "chat", unread=0),
            MockDialog(1005, "Work Project Updates", "group", unread=0, pinned=True),
            MockDialog(1006, "Archived Crypto News", "channel", unread=0, archived=True),
        ]

    async def get_entity(self, id):
        class MockEntity:
            def __init__(self, id): self.id = id
        return MockEntity(id)

    async def get_input_entity(self, entity):
        return entity

    async def delete_dialog(self, entity, revoke=False):
        pass

    async def qr_login(self):
        class MockQR:
            url = "tg://qr?token=mocktoken"
            async def wait(self): await asyncio.sleep(999)
            async def recreate(self): pass
        return MockQR()

    async def __call__(self, request):
        class MockTokenResult:
            def __init__(self): self.token = b"mock_token_bytes_sandbox_12345"
        return MockTokenResult()


# ── Load Config ───────────────────────────────────────────────────────────────
SANDBOX_MODE = False
api_id_str  = os.environ.get("API_ID", "")
api_hash_str = os.environ.get("API_HASH", "")

if not api_id_str or not api_hash_str:
    print("\n" + "="*70)
    print("[SANDBOX MODE] No API_ID / API_HASH found in environment.")
    print("  Local: fill in backend/data/backend.env")
    print("  Render: set API_ID and API_HASH in dashboard → Environment")
    print("="*70 + "\n")
    SANDBOX_MODE = True
    API_ID = 12345
    API_HASH = "sandbox_hash"
else:
    try:
        API_ID   = int(api_id_str)
        API_HASH = api_hash_str
    except ValueError:
        print("\n[INVALID API_ID] Falling back to sandbox mode\n")
        SANDBOX_MODE = True
        API_ID   = 12345
        API_HASH = "sandbox_hash"

PHONE        = os.environ.get("PHONE", "")
SESSION      = os.environ.get("SESSION_NAME", "my_account")
PORT         = int(os.environ.get("PORT", 3421))
LOGIN_METHOD = os.environ.get("LOGIN_METHOD", "phone")
RATE_LIMIT   = int(os.environ.get("ACTIONS_PER_MINUTE", 8))
FLOOD_BUFFER = int(os.environ.get("FLOOD_WAIT_BUFFER", 5))

# Storage: Render sets STORAGE_DIR=/var/data via render.yaml disk mount
STORAGE_DIR  = Path(os.environ.get("STORAGE_DIR", str(Path(__file__).parent / "data")))
SESSION_FILE = STORAGE_DIR / SESSION


# ── App Setup ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    c = get_client()
    await c.connect()
    print(f"[OK] LTMP backend running — sandbox={SANDBOX_MODE} port={PORT}")
    yield
    # Shutdown (nothing to clean up)

app = FastAPI(title="LTMP", docs_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client: TelegramClient = None
ws_clients: list[WebSocket] = []
login_state = {"step": "idle", "phone_code_hash": None}


# ── Helpers ───────────────────────────────────────────────────────────────────
async def broadcast(event: str, data: dict):
    msg = json.dumps({"event": event, "data": data})
    for ws in list(ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            ws_clients.remove(ws)


async def safe_action(fn, *args, **kwargs):
    """Call a Telethon function, auto-retrying on FloodWait."""
    while True:
        try:
            return await fn(*args, **kwargs)
        except FloodWaitError as e:
            wait = e.seconds + FLOOD_BUFFER
            await broadcast("flood_wait", {"seconds": wait})
            await asyncio.sleep(wait)


def get_client():
    global client
    if client is None:
        if SANDBOX_MODE:
            client = MockTelegramClient(str(SESSION_FILE), API_ID, API_HASH)
        else:
            STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    return client


cached_pfp = None
current_qr_login = None
current_qr_task = None


async def qr_waiter_task(qr_login_obj):
    try:
        await qr_login_obj.wait()
        login_state["step"] = "authorized"
    except asyncio.CancelledError:
        pass
    except SessionPasswordNeededError:
        login_state["step"] = "2fa_needed"
    except Exception as e:
        login_state["step"] = "idle"
        print("QR waiter error:", e)


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.get("/api/status")
async def status():
    global cached_pfp
    c = get_client()
    if not c.is_connected():
        await c.connect()

    authorized = await c.is_user_authorized()
    if authorized:
        login_state["step"] = "authorized"
        me = await c.get_me()
        pfp_base64 = None
        if not SANDBOX_MODE:
            if cached_pfp is None:
                try:
                    pfp_bytes = await c.download_profile_photo(me, file=bytes)
                    if pfp_bytes:
                        cached_pfp = base64.b64encode(pfp_bytes).decode("utf-8")
                except Exception:
                    pass
            pfp_base64 = cached_pfp
        return {
            "connected": True,
            "authorized": True,
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username,
            "phone": me.phone,
            "id": me.id,
            "pfp": pfp_base64,
        }
    return {
        "connected": True,
        "authorized": False,
        "step": login_state.get("step", "idle"),
    }


@app.post("/api/login/start")
async def login_start(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    c = get_client()
    await c.connect()

    if await c.is_user_authorized():
        return {"status": "already_authorized"}

    method = body.get("method", LOGIN_METHOD)

    if method == "qr":
        global current_qr_login, current_qr_task
        if current_qr_task and not current_qr_task.done():
            current_qr_task.cancel()

        current_qr_login = await c.qr_login()
        tg_url = current_qr_login.url

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(tg_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf)
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        login_state["step"] = "qr_pending"
        current_qr_task = asyncio.create_task(qr_waiter_task(current_qr_login))
        return {"status": "qr_generated", "qr_base64": qr_b64, "tg_url": tg_url}

    else:
        phone = body.get("phone", PHONE)
        sent = await c.send_code_request(phone)
        login_state["step"] = "code_sent"
        login_state["phone_code_hash"] = sent.phone_code_hash
        login_state["phone"] = phone
        return {"status": "code_sent"}


@app.post("/api/login/submit_code")
async def submit_code(body: dict):
    code = body.get("code", "").strip()
    c = get_client()
    try:
        await c.sign_in(
            phone=login_state["phone"],
            code=code,
            phone_code_hash=login_state["phone_code_hash"],
        )
        login_state["step"] = "authorized"
        me = await c.get_me()
        await broadcast("authorized", {"name": me.first_name})
        return {"status": "authorized"}
    except SessionPasswordNeededError:
        login_state["step"] = "2fa_needed"
        return {"status": "2fa_needed"}
    except PhoneCodeInvalidError:
        return {"status": "error", "message": "Invalid code, try again."}
    except PhoneCodeExpiredError:
        return {"status": "error", "message": "Code expired, restart login."}


@app.post("/api/login/submit_2fa")
async def submit_2fa(body: dict):
    c = get_client()
    try:
        await c.sign_in(password=body.get("password", ""))
        login_state["step"] = "authorized"
        me = await c.get_me()
        await broadcast("authorized", {"name": me.first_name})
        return {"status": "authorized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/logout")
async def logout():
    global client, cached_pfp, current_qr_login, current_qr_task
    if current_qr_task and not current_qr_task.done():
        current_qr_task.cancel()
    c = get_client()
    try:
        await c.log_out()
    except Exception:
        pass
    client = None
    cached_pfp = None
    current_qr_login = None
    current_qr_task = None
    # Clean up session files
    SESSION_FILE.with_suffix(".session").unlink(missing_ok=True)
    SESSION_FILE.with_suffix(".session-journal").unlink(missing_ok=True)
    login_state["step"] = "idle"
    return {"status": "logged_out"}


# ── Data Routes ───────────────────────────────────────────────────────────────
@app.get("/api/dialogs")
async def get_dialogs(limit: int = 100):
    c = get_client()
    if not await c.is_user_authorized():
        return {"error": "not_authorized"}
    dialogs = await c.get_dialogs(limit=limit)
    result = []
    for d in dialogs:
        result.append({
            "id": d.id,
            "name": d.name,
            "type": ("channel" if d.is_channel else "group" if d.is_group else "chat"),
            "unread": d.unread_count,
            "pinned": d.pinned,
            "archived": d.archived,
            "date": str(d.date) if d.date else None,
        })
    return {"dialogs": result}


@app.post("/api/dialogs/read_all")
async def read_all_dialogs(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    c = get_client()
    if not await c.is_user_authorized():
        return {"error": "not_authorized"}

    type_ = body.get("type", "all")
    dialogs = await c.get_dialogs(limit=200)
    count = 0

    for d in dialogs:
        if type_ == "group" and not d.is_group:
            continue
        if type_ == "channel" and not d.is_channel:
            continue
        if type_ == "chat" and (d.is_group or d.is_channel):
            continue

        if d.unread_count > 0:
            try:
                if SANDBOX_MODE:
                    pass  # mock — nothing to call
                else:
                    await c(ReadHistoryRequest(peer=d.entity, max_id=0))
                count += 1
            except Exception as e:
                print(f"Error marking {d.name} as read: {e}")

    return {"status": "ok", "marked_read": count}


@app.post("/api/dialog/leave")
async def leave_dialog(body: dict):
    c = get_client()
    dialogs = await c.get_dialogs()
    dialog = next((d for d in dialogs if d.id == int(body["id"])), None)
    if not dialog:
        try:
            entity = await c.get_entity(int(body["id"]))
            await safe_action(c.delete_dialog, entity)
            return {"status": "left", "id": body["id"]}
        except Exception as e:
            return {"status": "error", "message": f"Channel not found: {str(e)}"}
    await safe_action(c.delete_dialog, dialog.entity)
    return {"status": "left", "id": body["id"]}


@app.post("/api/dialog/archive")
async def archive_dialog(body: dict):
    from telethon.tl.functions.folders import EditPeerFoldersRequest
    from telethon.tl.types import InputFolderPeer
    c = get_client()
    dialogs = await c.get_dialogs()
    dialog = next((d for d in dialogs if d.id == int(body["id"])), None)
    if not dialog:
        try:
            entity = await c.get_entity(int(body["id"]))
            peer = await c.get_input_entity(entity)
        except Exception as e:
            return {"status": "error", "message": f"Channel not found: {str(e)}"}
    else:
        peer = await c.get_input_entity(dialog.entity)

    await c(EditPeerFoldersRequest(
        folder_peers=[InputFolderPeer(peer=peer, folder_id=1)]
    ))
    return {"status": "archived", "id": body["id"]}


@app.post("/api/dialog/delete_history")
async def delete_history(body: dict):
    c = get_client()
    dialogs = await c.get_dialogs()
    dialog = next((d for d in dialogs if d.id == int(body["id"])), None)
    if not dialog:
        try:
            entity = await c.get_entity(int(body["id"]))
            await safe_action(c.delete_dialog, entity, revoke=body.get("revoke", False))
            return {"status": "deleted", "id": body["id"]}
        except Exception as e:
            return {"status": "error", "message": f"Chat not found: {str(e)}"}
    await safe_action(c.delete_dialog, dialog.entity, revoke=body.get("revoke", False))
    return {"status": "deleted", "id": body["id"]}


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in ws_clients:
            ws_clients.remove(ws)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False, log_level="info")
