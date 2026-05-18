# TGControl — Personal Telegram Manager
A local tool to manage **your own** Telegram account. Runs entirely on your PC.

---

## ⚡ Quick Start (Windows)

### Step 1 — Get API credentials
1. Go to **https://my.telegram.org**
2. Log in with your phone number
3. Click **API Development Tools**
4. Create an app (any name/description is fine)
5. Copy your **App api_id** and **App api_hash**

### Step 2 — Configure
Open **`config.js`** in any text editor (Notepad works) and fill in:
```js
api_id:   "12345678",          // your api_id from my.telegram.org
api_hash: "abcdef...",         // your api_hash
login_method: "phone",         // "phone" or "qr"
phone:    "+919876543210",     // your number (if using phone method)
```

### Step 3 — First time setup
Double-click **`setup.bat`** — this installs Python packages.

### Step 4 — Run
Double-click **`start.bat`** — then open **http://localhost:3421** in your browser.

---

## 📱 Login Methods

**Phone + OTP** (recommended)
- Enter your phone number in the UI
- Receive a code in Telegram or SMS
- Enter the code

**QR Code**
- Set `login_method: "qr"` in config.js
- Open Telegram on your phone → Settings → Devices → Link Desktop
- Scan the QR shown in the browser

---

## 🔒 Security Notes
- Your session is saved locally in `data/` as a `.session` file
- Nothing is sent to any server — all traffic goes directly to Telegram
- Your API credentials stay only in `config.js` on your PC

---

## Requirements
- Python 3.9 or newer — https://python.org/downloads
- Any modern browser (Chrome, Edge, Firefox)
- Your own Telegram account
