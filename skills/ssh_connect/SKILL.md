# Skill: Remote Server Connection (SSH)

This skill describes how to use the `backend/ssh_connect.py` utility to interact with remote servers over SSH.

## Purpose
To provide a reliable and reusable way to connect to remote servers (like VPN nodes) and execute shell commands for management, monitoring, or configuration.

## Component
- **File:** `backend/ssh_connect.py`
- **Dependency:** `paramiko`

## Capabilities

### 1. Direct CLI Usage
You can run the script directly from the terminal to execute commands on the default remote server.

**Command:**
```bash
python3 backend/ssh_connect.py "<command>"
```

**Example:**
```bash
python3 backend/ssh_connect.py "df -h"
```

### 2. Python API Usage
The `SSHConnector` class can be imported and used in other backend services (e.g., in `server_manager`).

**Initialization:**
```python
from backend.ssh_connect import SSHConnector

ssh = SSHConnector(
    host="92.118.232.155",
    username="root",
    password="your_password",
    port=22
)
```

**Methods:**
- `connect()`: Establishes the SSH connection. Returns `True` if successful.
- `execute(command, timeout=60)`: Executes a shell command. Returns `(stdout, stderr, exit_code)`.
- `close()`: Closes the connection.

**Example Implementation:**
```python
if ssh.connect():
    stdout, stderr, code = ssh.execute("uptime")
    if code == 0:
        print(f"Server Uptime: {stdout.strip()}")
    ssh.close()
```

## Security & Best Practices
- **Hardcoded Credentials:** The script currently contains default credentials in the `if __name__ == "__main__":` block. **Never** use these in production; always use environment variables or a secret manager.
- **Error Handling:** The `execute` method returns `None, "Not connected", -1` if the connection is lost.
- **Timeouts:** Default connection timeout is 15 seconds; command execution timeout is 60 seconds.

## Related Tasks
- Deploying VPN configurations.
- Monitoring server status.
- Running maintenance scripts on remote nodes.
