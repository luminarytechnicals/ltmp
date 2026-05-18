"""
LTMP — Luminary Telegram Management Panel Local Backend
Runs on localhost only. Uses Telethon to connect to your Telegram account.
Start with: python engine/server.py
"""

import asyncio
import json
import os
import sys
import qrcode
import io
import base64
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeExpiredError,
    PhoneCodeInvalidError, FloodWaitError
)
from telethon.tl.functions.auth import ExportLoginTokenRequest
from telethon.tl.types import auth

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

class MockSentCode:
    def __init__(self):
        self.phone_code_hash = "mock_hash_12345"

class MockTelegramClient:
    def __init__(self, session, api_id, api_hash):
        self._connected = False
        self._authorized = False
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash

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
            raise PhoneCodeInvalidError("Invalid code. Use code '12345' for sandbox.")

    async def log_out(self):
        self._authorized = False

    async def get_dialogs(self, limit=100):
        # Return a list of interesting mock dialogs for the user to test bulk operations
        return [
            MockDialog(1001, "Tech Hackers Channel", "channel", unread=27),
            MockDialog(1002, "Global Tech Community", "group", unread=8),
            MockDialog(1003, "Spam Channel", "channel", unread=142),
            MockDialog(1004, "Developer Abhinav", "chat", unread=0),
            MockDialog(1005, "Work Project Updates", "group", unread=0, pinned=True),
            MockDialog(1006, "Archived Crypto News", "channel", unread=0, archived=True),
        ]

    async def get_entity(self, id):
        class MockEntity:
            def __init__(self, id):
                self.id = id
        return MockEntity(id)

    async def delete_dialog(self, entity, revoke=False):
        pass

    async def __call__(self, request):
        class MockTokenResult:
            def __init__(self):
                self.token = b"mock_token_bytes_sandbox_12345"
        return MockTokenResult()


# ── load config ──────────────────────────────────────────────────────────────
config_path = Path(__file__).parent.parent / "config.js"
import re
cfg = {}
try:
    for line in config_path.read_text(encoding="utf-8").splitlines():
        # strip single-line comments
        line = re.sub(r'//.*', '', line).strip()
        if not line:
            continue
        # look for key: value (handles optional single/double quotes around keys)
        match = re.match(r'^\s*(?:\'([^\']+)\'|"([^"]+)"|([a-zA-Z_][a-zA-Z0-9_]*))\s*:\s*(.*?)\s*,?\s*$', line)
        if match:
            key = match.group(1) or match.group(2) or match.group(3)
            val = match.group(4).strip()
            # strip quotes if string
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            cfg[key] = val
except Exception as e:
    print(f"[ERROR] Failed to read config.js: {e}")
    sys.exit(1)

SANDBOX_MODE = False
api_id_str = cfg.get("api_id", "")
api_hash_str = cfg.get("api_hash", "")

if api_id_str == "YOUR_API_ID" or not api_id_str or api_hash_str == "YOUR_API_HASH" or not api_hash_str:
    print("\n" + "="*70)
    print("[SANDBOX SIMULATION MODE ACTIVE]")
    print("   No real Telegram credentials found in config.js.")
    print("   Starting in Simulated Offline Mode for local browser testing!")
    print("   To log in, use the code '12345' (or scan the simulated QR code).")
    print("="*70 + "\n")
    SANDBOX_MODE = True
    API_ID = 12345
    API_HASH = "sandbox_hash"
else:
    try:
        API_ID = int(api_id_str)
        API_HASH = api_hash_str
    except ValueError:
        print("\n" + "="*70)
        print("[INVALID CREDENTIALS -> FALLING BACK TO SANDBOX MODE]")
        print("="*70 + "\n")
        SANDBOX_MODE = True
        API_ID = 12345
        API_HASH = "sandbox_hash"

PHONE    = cfg.get("phone", "")
if PHONE == "+91XXXXXXXXXX":
    PHONE = ""

SESSION  = cfg.get("session_name", "my_account")
PORT     = int(cfg.get("port", 3421))
LOGIN_METHOD = cfg.get("login_method", "phone")
RATE_LIMIT   = int(cfg.get("actions_per_minute", 8))
FLOOD_BUFFER = int(cfg.get("flood_wait_buffer", 5))

SESSION_FILE = Path(__file__).parent.parent / "data" / SESSION

# ── app setup ────────────────────────────────────────────────────────────────
app = FastAPI(title="LTMP", docs_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

client: TelegramClient = None
ws_clients: list[WebSocket] = []
login_state = {"step": "idle", "phone_code_hash": None}

# ── helpers ──────────────────────────────────────────────────────────────────
async def broadcast(event: str, data: dict):
    msg = json.dumps({"event": event, "data": data})
    for ws in list(ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            ws_clients.remove(ws)

async def safe_action(coro):
    """Run a Telethon call, handling FloodWait automatically."""
    if SANDBOX_MODE:
        return await coro
    while True:
        try:
            return await coro
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
            Path(SESSION_FILE).parent.mkdir(parents=True, exist_ok=True)
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
        print("QR waiter background task error:", e)

# ── auth routes ───────────────────────────────────────────────────────────────
@app.get("/api/status")
async def status():
    global cached_pfp
    c = get_client()
    if not c.is_connected():
        return {"connected": False, "authorized": False}

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
                        cached_pfp = base64.b64encode(pfp_bytes).decode('utf-8')
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
        "step": login_state.get("step", "idle")
    }


@app.post("/api/login/start")
async def login_start(body: dict = {}):
    """Step 1 — connect and begin login flow."""
    c = get_client()
    await c.connect()

    if await c.is_user_authorized():
        return {"status": "already_authorized"}

    method = body.get("method", LOGIN_METHOD)

    if method == "qr":
        global current_qr_login, current_qr_task
        # Cancel any previous background QR waiter task
        if current_qr_task and not current_qr_task.done():
            current_qr_task.cancel()

        # Initiate high-level QR login procedure
        current_qr_login = await c.qr_login()
        tg_url = current_qr_login.url
 
        # render QR as base64 PNG
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
        # phone flow
        phone = body.get("phone", PHONE)
        sent = await c.send_code_request(phone)
        login_state["step"] = "code_sent"
        login_state["phone_code_hash"] = sent.phone_code_hash
        login_state["phone"] = phone
        return {"status": "code_sent"}


@app.post("/api/login/submit_code")
async def submit_code(body: dict):
    """Step 2 — submit OTP code."""
    code = body.get("code", "").strip()
    c = get_client()
    try:
        await c.sign_in(
            phone=login_state["phone"],
            code=code,
            phone_code_hash=login_state["phone_code_hash"]
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
    """Step 3 (optional) — submit 2FA password."""
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
    SESSION_FILE.with_suffix(".session").unlink(missing_ok=True)
    login_state["step"] = "idle"
    return {"status": "logged_out"}


# ── data routes ───────────────────────────────────────────────────────────────
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
            "type": ("channel" if d.is_channel else
                     "group" if d.is_group else "chat"),
            "unread": d.unread_count,
            "pinned": d.pinned,
            "archived": d.archived,
            "date": str(d.date) if d.date else None,
        })
    return {"dialogs": result}


@app.post("/api/dialogs/read_all")
async def read_all_dialogs(body: dict = {}):
    c = get_client()
    if not await c.is_user_authorized():
        return {"error": "not_authorized"}
    
    type_ = body.get("type", "all") # "all", "group", "channel", "chat"
    dialogs = await c.get_dialogs(limit=200)
    count = 0
    
    for d in dialogs:
        # Check type filter
        if type_ == "group" and not d.is_group:
            continue
        if type_ == "channel" and not d.is_channel:
            continue
        if type_ == "chat" and (d.is_group or d.is_channel):
            continue
        
        if d.unread_count > 0:
            try:
                await c.send_read_acknowledge(d.entity)
                count += 1
            except Exception as e:
                print(f"Error marking {d.name} as read: {e}")
                
    return {"status": "ok", "marked_read": count}


@app.post("/api/dialog/leave")
async def leave_dialog(body: dict):
    """Leave a single channel/group by ID."""
    c = get_client()
    dialogs = await c.get_dialogs()
    dialog = next((d for d in dialogs if d.id == int(body["id"])), None)
    if not dialog:
        # Fallback to get_entity if not in immediate dialogs list
        try:
            entity = await c.get_entity(int(body["id"]))
            await safe_action(c.delete_dialog(entity))
            return {"status": "left", "id": body["id"]}
        except Exception as e:
            return {"status": "error", "message": f"Channel not found: {str(e)}"}
    await safe_action(c.delete_dialog(dialog.entity))
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
    """Delete all messages in a private chat."""
    c = get_client()
    dialogs = await c.get_dialogs()
    dialog = next((d for d in dialogs if d.id == int(body["id"])), None)
    if not dialog:
        try:
            entity = await c.get_entity(int(body["id"]))
            await safe_action(c.delete_dialog(entity, revoke=body.get("revoke", False)))
            return {"status": "deleted", "id": body["id"]}
        except Exception as e:
            return {"status": "error", "message": f"Chat not found: {str(e)}"}
    await safe_action(c.delete_dialog(dialog.entity, revoke=body.get("revoke", False)))
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
        ws_clients.remove(ws)


# ── startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    c = get_client()
    await c.connect()
    print(f"[OK] LTMP (Luminary Telegram Management Panel) running at http://localhost:{PORT}")
    print("   Open your browser at http://localhost:{PORT}".format(PORT=PORT))


# serve the frontend HTML + config.js
from static import mount_frontend
mount_frontend(app)


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=PORT,
                reload=False, log_level="info")
