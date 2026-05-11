"""SSH-based 3x-ui installer.

Connects via paramiko, runs the official MHSanaei install.sh non-interactively,
then overrides credentials/port/paths via the x-ui binary directly
(/usr/local/x-ui/x-ui setting).  The /usr/bin/x-ui shell wrapper in newer
versions does not relay the `setting` subcommand to the binary, so we bypass it.
"""

import asyncio
import logging
import re
import time
import secrets
import shlex
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import paramiko

logger = logging.getLogger(__name__)

# Matches ANSI CSI/OSC escape sequences.
_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@dataclass
class SshTarget:
    host: str
    username: str
    password: str
    port: int = 22


@dataclass
class InstallOutcome:
    panel_user: str
    panel_password: str
    panel_port: int
    panel_web_base_path: str
    panel_url: str
    server_public_host: str
    sub_port: int
    log: str


def _random_panel_port() -> int:
    return secrets.choice(range(40000, 60000))


def _random_path(length: int = 16) -> str:
    return secrets.token_hex(length // 2)


def _random_password(length: int = 24) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_username() -> str:
    return f"mvm-{secrets.token_hex(4)}"


@dataclass
class _Recorder:
    lines: List[str] = field(default_factory=list)
    progress_cb: Optional[Callable[[str], None]] = None

    def write(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        self.lines.append(line)
        if self.progress_cb is not None:
            try:
                self.progress_cb(line)
            except Exception:  # noqa: BLE001 - never let progress reporting break install
                logger.exception("progress_cb raised")

    def text(self, max_chars: int = 16000) -> str:
        joined = "\n".join(self.lines)
        if len(joined) <= max_chars:
            return joined
        return joined[-max_chars:]


def _run(
    client: paramiko.SSHClient,
    command: str,
    recorder: _Recorder,
    *,
    timeout: float = 600.0,
    sudo_password: Optional[str] = None,
) -> Tuple[int, str]:
    recorder.write(f"$ {command}")
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("ssh transport closed")
    channel = transport.open_session()
    try:
        channel.settimeout(timeout)
        channel.get_pty()
        channel.exec_command(command)
        if sudo_password:
            try:
                channel.send(f"{sudo_password}\n")
            except OSError:
                pass
        chunks: List[bytes] = []
        while True:
            if channel.recv_ready():
                data = channel.recv(65536)
                if data:
                    chunks.append(data)
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        recorder.write(line)
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(65536)
                if data:
                    chunks.append(data)
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        recorder.write(line)
            if channel.exit_status_ready() and not (
                channel.recv_ready() or channel.recv_stderr_ready()
            ):
                break
        exit_code = channel.recv_exit_status()
        full = b"".join(chunks).decode("utf-8", errors="replace")
        return exit_code, full
    finally:
        channel.close()


async def run_install(
    target: SshTarget,
    *,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> InstallOutcome:
    """Synchronous-but-blocking install run inside a thread."""
    return await asyncio.to_thread(_run_install_sync, target, progress_cb)


def _run_install_sync(
    target: SshTarget,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> InstallOutcome:
    panel_user = _random_username()
    panel_password = _random_password()
    panel_port = _random_panel_port()
    panel_path = _random_path(16)
    # x-ui v2.9.3 ignores -subPort in the setting command and always starts its
    # subscription listener on its built-in default port 2096.
    sub_port = 2096

    recorder = _Recorder(progress_cb=progress_cb)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=target.host,
            port=target.port,
            username=target.username,
            password=target.password,
            timeout=30.0,
            allow_agent=False,
            look_for_keys=False,
        )

        sudo = "" if target.username == "root" else f"echo {shlex.quote(target.password)} | sudo -S "

        # 1) Make sure curl + bash are present.
        for command in (
            f"{sudo}bash -c 'export DEBIAN_FRONTEND=noninteractive && apt-get update -y'",
            f"{sudo}bash -c 'export DEBIAN_FRONTEND=noninteractive && apt-get install -y curl ca-certificates'",
        ):
            code, _ = _run(client, command, recorder)
            if code != 0:
                raise RuntimeError(f"prep step failed (exit {code}): {command!r}")

        # 2) Run the official install script.
        #    Prompts (fresh install, in order):
        #      [1] "Would you like to customize the Panel Port?" [y/n] → \n (random)
        #      [2] "Choose SSL certificate method (default 2 for IP)"  → \n (IP cert)
        #      [3] "Do you have an IPv6 address to include?"            → \n (skip)
        #      [4] "Port to use for ACME HTTP-01 listener (default 80)"→ \n (port 80)
        stdin_answers = r"\n\n\n\n\n"
        install_command = (
            f"{sudo}bash -c \""
            f"printf '{stdin_answers}' | "
            "bash <(curl -Ls https://raw.githubusercontent.com/MHSanaei/3x-ui/refs/tags/v3.0.1/install.sh)"
            "\""
        )
        logger.info("running 3x-ui install script")
        code, _ = _run(client, install_command, recorder, timeout=900.0)
        logger.info("install script exit_code=%s", code)
        if code != 0:
            raise RuntimeError(f"3x-ui install script failed (exit {code})")

        # 3) Override credentials via the binary directly.
        #    /usr/bin/x-ui is a shell wrapper whose newer versions do NOT relay
        #    the `setting` subcommand to the binary, so we call the binary at its
        #    fixed install path instead.
        xui_bin = "/usr/local/x-ui/x-ui"
        setting_cmd = (
            f"{sudo}{xui_bin} setting"
            f" -username {shlex.quote(panel_user)}"
            f" -password {shlex.quote(panel_password)}"
            f" -port {panel_port}"
            f" -webBasePath {shlex.quote(panel_path)}"
        )
        logger.info(
            "applying credentials via binary: user=%s port=%s path=%s sub_port=%s(fixed)",
            panel_user, panel_port, panel_path, sub_port,
        )
        code, setting_out = _run(client, setting_cmd, recorder)
        logger.info("setting exit_code=%s output=%s", code, _strip_ansi(setting_out)[:400])
        if code != 0:
            raise RuntimeError(f"x-ui setting failed (exit {code})")

        # 4) Restart so all settings take effect.
        restarted = False
        for restart_cmd in (
            f"{sudo}{xui_bin} restart",
            f"{sudo}systemctl restart x-ui",
        ):
            code, _ = _run(client, restart_cmd, recorder)
            if code == 0:
                logger.info("x-ui restarted via: %s", restart_cmd)
                restarted = True
                break
        if not restarted:
            logger.warning("x-ui restart returned non-zero; panel may not be running")


        time.sleep(10)
        _run(client, 'x-ui restart', recorder, timeout=60.0)
        time.sleep(30)
        
        
        public_host = target.host
        panel_url = f"https://{public_host}:{panel_port}/{panel_path}"
        logger.info("install complete panel_url=%s sub_port=%s", panel_url, sub_port)
        return InstallOutcome(
            panel_user=panel_user,
            panel_password=panel_password,
            panel_port=panel_port,
            panel_web_base_path=panel_path,
            panel_url=panel_url,
            server_public_host=public_host,
            sub_port=sub_port,
            log=recorder.text(),
        )
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
