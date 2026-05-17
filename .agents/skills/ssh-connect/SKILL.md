---
name: ssh-connect
description: >
  Connect to remote SSH servers using the project's paramiko-based SSHConnector class.
  Use when Kimi needs to execute commands, manage servers, deploy services, run diagnostics,
  transfer files, or perform any maintenance tasks on remote SSH-accessible hosts in the MVMVpn project.
  Triggers: SSH, remote server, VPS, deploy, execute command, server management, paramiko.
---

# SSH Connect Skill

Provides procedural knowledge for using the project's `SSHConnector` class to interact with remote servers.

## Quick Start

Import and use the connector from the project root:

```python
import sys
sys.path.insert(0, "backend")
from ssh_connect import SSHConnector

ssh = SSHConnector(host="92.118.232.155", username="root", password="...", port=22)
if ssh.connect():
    stdout, stderr, code = ssh.execute("uname -a")
    print(stdout)
    ssh.close()
```

For the default project VPS, credentials are defined in `backend/ssh_connect.py` under `__main__`.

## SSHConnector API

| Method | Returns | Description |
|--------|---------|-------------|
| `connect()` | `bool` | Opens SSH connection. Auto-adds host keys. Returns `True` on success. |
| `execute(command, timeout=60)` | `(stdout, stderr, exit_code)` | Runs a remote command. Reconnects automatically if disconnected. |
| `close()` | `None` | Closes the connection. |

### Error Handling

- `execute()` returns `(None, error_message, -1)` on failure.
- Check `exit_code != 0` or non-empty `stderr` for command errors.
- Connection errors are logged via the `SSHConnector` logger.

## Common Workflows

### Execute a Single Command

```python
stdout, stderr, code = ssh.execute("systemctl status mvm-server-manager")
```

### Execute Multiple Commands

Prefer a single shell string with `&&` or `;` to reduce connection overhead:

```python
cmds = "cd /opt/mvm/backend && git pull && ./deploy.sh"
stdout, stderr, code = ssh.execute(cmds, timeout=120)
```

### Check Server Health

```python
stdout, _, _ = ssh.execute("uptime && free -h && df -h")
```

### Deploy Backend

The project has `backend/deploy.sh`. Typical deploy flow:

```python
ssh.execute("cd /opt/mvm && git pull origin main")
ssh.execute("cd /opt/mvm/backend && bash deploy.sh", timeout=300)
```

### File Transfers (SFTP)

`SSHConnector` exposes the underlying `paramiko.SSHClient` as `.client`. Use it to open an SFTP session:

```python
sftp = ssh.client.open_sftp()
sftp.put("local_file.txt", "/remote/path/file.txt")
sftp.get("/remote/path/file.txt", "local_file.txt")
sftp.close()
```

## Context Manager Pattern

For robust resource cleanup, wrap usage in a context manager:

```python
from contextlib import contextmanager

@contextmanager
def ssh_session(host, username, password, port=22):
    conn = SSHConnector(host, username, password, port)
    try:
        if conn.connect():
            yield conn
        else:
            raise ConnectionError(f"Failed to connect to {host}")
    finally:
        conn.close()

with ssh_session("92.118.232.155", "root", "...") as ssh:
    out, err, code = ssh.execute("docker ps")
```

## Project-Specific Notes

- **Primary VPS**: `92.118.232.155` (managed in `backend/ssh_connect.py`).
- **Backend services**: `mvm-server-manager.service`, `mvm-tg-bot.service`, `mvm-vk-bot.service`, `mvm-admin-bot.service`.
- **Deploy script**: `backend/deploy.sh` handles rsync, venv setup, and systemd restarts.
- **Monitoring stack**: Prometheus + Grafana run via `backend/monitoring/docker-compose.yml`.

## Requirements

- `paramiko` must be installed (`pip install paramiko`).
- Ensure the target host allows password authentication or configure key-based auth in `ssh_connect.py` if needed.
