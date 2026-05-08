# MVM VPN Backend Deployment

This directory contains the backend services (Telegram Bot, VK Bot, and Server Manager) and the deployment tools.

## Structure
- `bot/`: Telegram and VK bots code.
- `server_manager/`: FastAPI-based server manager.
- `deploy.sh`: Local deployment script.
- `.github/workflows/deploy-backend.yml`: GitHub Actions auto-deployment.

## Manual Deployment
To deploy manually from your machine:
1. Ensure you have SSH access to `92.118.232.155`.
2. Run:
   ```bash
   chmod +x backend/deploy.sh
   ./backend/deploy.sh
   ```

## CI/CD Setup
1. Go to your GitHub Repository Settings.
2. Navigate to **Secrets and variables** > **Actions**.
3. Add the following secrets:
   - **`SSH_PRIVATE_KEY`**: Your private SSH key (the one matching the public key added to the server).
   - **`REMOTE_HOST`**: `92.118.232.155`
   - **`REMOTE_USER`**: `root`

The workflow will trigger automatically whenever you push changes to the `backend/` directory on the `main` branch.

## Server Management
The following services are managed by this deployment:
- `mvm-tg-bot.service`
- `mvm-vk-bot.service`
- `mvm-server-manager.service`

You can check their status on the server with:
```bash
systemctl status mvm-tg-bot mvm-vk-bot mvm-server-manager
```
And view logs:
```bash
journalctl -u mvm-tg-bot -f
```
