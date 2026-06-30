# remnawave_webhook_server

FastAPI service that handles user-related webhook events sent by the Remnawave panel.

## Responsibilities

- Receive and handle webhook events from Remnawave with the `user` scope (such as `user.created`, `user.deleted`, `user.enabled`, `user.disabled`, `user.revoked`, `user.limited`, `user.expired`, `user.traffic_reset`, `user.expiration`, `user.not_connected`, `user.bandwidth_usage_threshold_reached`).
- Authenticate incoming webhooks using the `x-remnawave-signature` header (HMAC-SHA256 of the raw body payload using a shared webhook secret).
- Retrieve matching users from the Firestore `users` collection using their Remnawave UUID or username (derived from Firebase Auth UID).
- Format and send localized notifications (supporting English, Russian, and Persian) via Telegram or VK by invoking helper functions from the sibling bot code (`mvm_bot`).

## File Structure

- `app.py` — FastAPI app definition, endpoints (`POST /webhook`, `GET /health`), signature verification, and event processing logic.
- `config.py` — Config loader that reads webhook settings, Telegram credentials, and Firebase config.
- `notifications.py` — Imports the bot's telegram/VK notification dispatch logic directly from the sibling `bot` package.
- `__main__.py` — Entry point that runs the app using Uvicorn.
- `requirements.txt` — Package dependencies.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r remnawave_webhook_server/requirements.txt
# Set up env variables (or let it read from ../bot/.env or ../server_manager/.env)
REMNAWAVE_WEBHOOK_HOST=0.0.0.0
REMNAWAVE_WEBHOOK_PORT=8082
REMNAWAVE_WEBHOOK_SECRET=your-64-character-webhook-secret
python3 -m remnawave_webhook_server
```

## Environment Variables

- `REMNAWAVE_WEBHOOK_HOST` (default: `0.0.0.0`): Host address the server binds to.
- `REMNAWAVE_WEBHOOK_PORT` (default: `8082`): Port on which the webhook server runs.
- `REMNAWAVE_WEBHOOK_SECRET` or `WEBHOOK_SECRET_HEADER`: HMAC-SHA256 signature key configured in the Remnawave panel settings.
- `TELEGRAM_BOT_TOKEN` or `BOT_TOKEN`: Token for the Telegram bot to send notifications.
- `FIREBASE_SERVICE_ACCOUNT_PATH`: Path to the Firebase service account key JSON file.

## Webhook Verification

Remnawave signs webhook payloads. If a webhook secret is configured:
1. The server reads the raw request payload bytes.
2. It generates an HMAC-SHA256 hash using the secret key.
3. It compares this hash using a constant-time comparison against the value of the `X-Remnawave-Signature` header.
4. Requests with missing or invalid signatures are rejected with a `401 Unauthorized` status.
