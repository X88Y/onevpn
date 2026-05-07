# server_manager

Long-running Python service that owns the VPN server pool.

Responsibilities:

- SSH into newly added servers (admin Telegram bot calls `POST /servers`) and
  install [3x-ui (MHSanaei)](https://github.com/MHSanaei/3x-ui) non-interactively.
- Talk to each server's 3x-ui panel API to add / delete / inspect clients.
- Maintain `vpn_servers`, `vpn_clients`, `vpn_install_jobs` collections in
  Firestore.
- Provide an aggregated subscription endpoint at `${MANAGER_PUBLIC_URL}/sub/{subId}`
  that fans out to every healthy server's panel subscription URL and
  concatenates VLESS lines into a single body.

Components:

- `app.py` — FastAPI app + lifespan that starts background workers.
- `routes/servers.py` — admin endpoints for managing the pool.
- `routes/clients.py` — `provision`, `regenerate`, traffic.
- `routes/subscription.py` — public `GET /sub/{subId}` aggregator.
- `workers/install_worker.py` — drains `vpn_install_jobs`.
- `workers/traffic_sync.py` — periodic per-user traffic refresh.
- `workers/health.py` — periodic panel health pings.
- `xui/` — 3x-ui panel client + Reality inbound template.
- `ssh/installer.py` — paramiko-driven install of 3x-ui.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server_manager/requirements.txt
cp server_manager/.env.example server_manager/.env
python -m server_manager.gen_fernet_key
# put the printed value into SERVER_MANAGER_FERNET_KEY in server_manager/.env
# (Fernet is only loaded when encrypting; you can generate a key even while
#  .env still has a placeholder, or use: from server_manager.crypto import
#  generate_key — same output.)
python -m server_manager
```

The service requires Firebase admin credentials. Either set
`FIREBASE_SERVICE_ACCOUNT_PATH` in `.env` or rely on
`GOOGLE_APPLICATION_CREDENTIALS`.

## Authentication

Every endpoint except `GET /healthz` and `GET /sub/{subId}` requires
`X-API-Key: ${MANAGER_API_KEY}`. Cloud Functions and `bot_admin` send the
same key.

## Migration from `vpn_keys`

The legacy `vpn_keys` Firestore collection is no longer read by Cloud
Functions. The new flow is:

1. Admin runs `/add_server` in the admin Telegram bot. The bot collects
   IP and SSH password (port 22, user `root`) and POSTs to
   `${MANAGER_BASE_URL}/servers`.
2. The manager's install worker drains `vpn_install_jobs`, SSHes in,
   runs the official MHSanaei/3x-ui install script non-interactively,
   randomizes panel credentials and ports via `x-ui setting`, then probes
   the panel HTTP API to register a default VLESS+Reality inbound. On
   success the bot prints one-time panel credentials.
3. End-user app calls the existing `getRandomVpnKey` Cloud Function. It
   resolves the user, verifies an active subscription, and asks the
   manager to provision (idempotent) — returning a stable
   `${MANAGER_PUBLIC_URL}/sub/{subId}` URL pointing to the aggregator
   endpoint. Each user gets a unique `subId` and a unique VLESS UUID per
   server.
4. End-user app can also call `regenerateVpnKey` to rotate the subId and
   every per-server UUID. The manager enforces a cooldown
   (`REGENERATE_COOLDOWN_S`, 60s by default).
5. `getMyVpnUsage` returns aggregated traffic counters refreshed by the
   manager's `traffic_sync` worker.

Once the new flow is healthy, the `vpn_keys` Firestore collection can be
deleted manually. The legacy `/add_vpn_key` admin command is left in the
code but removed from the Telegram bot command menu.

## Cloud Functions configuration

In `firebase functions:secrets:set MANAGER_API_KEY` set the same value as
`server_manager/.env::MANAGER_API_KEY`. Define `MANAGER_BASE_URL` as a
project parameter via `firebase functions:config:set` or by passing
`--params MANAGER_BASE_URL=https://manager.example.com` to deploy.

## bot_admin configuration

Add to `bot_admin/.env`:

```
MANAGER_BASE_URL=https://manager.example.com
MANAGER_API_KEY=<same value as server_manager/.env>
```
