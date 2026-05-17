# Project-Specific SSH Examples

## Service Management

Check all MVM services:

```bash
systemctl status mvm-server-manager mvm-tg-bot mvm-vk-bot mvm-admin-bot
```

Restart a service after code changes:

```bash
systemctl restart mvm-server-manager
```

View recent logs:

```bash
journalctl -u mvm-server-manager -n 50 --no-pager
```

## Docker / Monitoring

The monitoring stack runs in Docker:

```bash
cd /opt/mvm/backend/monitoring && docker-compose ps
docker-compose logs prometheus --tail=50
docker-compose restart grafana
```

## Python Environment

Backend services run in a virtual environment:

```bash
source /opt/mvm/backend/server_manager/venv/bin/activate
python -m pip list
```

## Firewall / Network

```bash
ufw status
ss -tlnp | grep -E '22|8000|3000|9090'
```

## Troubleshooting

| Symptom | Diagnostic Command |
|---------|-------------------|
| Service won't start | `journalctl -u <service> -xe` |
| Out of disk space | `df -h` and `du -sh /opt/mvm/*` |
| High memory usage | `free -h && ps aux --sort=-%mem \| head` |
| Network issues | `ping 8.8.8.8 && curl -I https://google.com` |
