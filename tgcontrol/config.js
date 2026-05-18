// ============================================================
//  LTMP (Luminary Telegram Management Panel) — Personal Configuration
//  Get your API credentials from https://my.telegram.org
//  Login > API Development Tools > Create App
// ============================================================

module.exports = {

  // --- TELEGRAM API CREDENTIALS (required) -----------------
  // Go to https://my.telegram.org → API Development Tools
  api_id: "34288958",          // e.g. "12345678"
  api_hash: "7db40aecd05241d96b2e91ea953e35fa",      // e.g. "abcdef1234567890abcdef1234567890"

  // --- LOGIN METHOD ----------------------------------------
  // "phone"  → enter phone number + OTP SMS code
  // "qr"     → scan QR code in Telegram app (Settings → Devices → Link Desktop)
  login_method: "phone",          // "phone" or "qr"

  phone: "",         // e.g. "+918294721929"

  // --- SESSION -------------------------------------------------
  // Your session is saved locally as an encrypted file.
  // Once logged in, you won't need to log in again.
  session_name: "my_account",     // name for local session file (no spaces)

  // --- SERVER --------------------------------------------------
  port: 3421,                     // local server port (localhost:3421)

  // --- SAFETY LIMITS ------------------------------------------
  // These protect you from Telegram flood bans.
  // Do not set higher than defaults.
  actions_per_minute: 8,          // max actions per minute (Telegram safe limit: ~10)
  flood_wait_buffer: 5,           // extra seconds added to any flood-wait

};
