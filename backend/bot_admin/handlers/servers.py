import asyncio
import contextlib
import logging
from html import escape
from typing import Optional

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot_admin.config import admin_telegram_ids
from bot_admin import manager_client

logger = logging.getLogger(__name__)
router = Router(name="servers")

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "root"


class AddServer(StatesGroup):
    host = State()
    password = State()


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


async def _delete_message(message: Message) -> None:
    with contextlib.suppress(Exception):
        await message.delete()


@router.message(Command("add_server"))
async def cmd_add_server(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.clear()
    await state.set_state(AddServer.host)
    await message.answer(
        "Step 1/2: send the server IP or hostname.\n"
        "SSH uses port 22 and user <code>root</code>.\n"
        "Send /cancel at any time to abort.",
        parse_mode="HTML",
    )


@router.message(AddServer.host, F.text)
async def add_step_host(message: Message, state: FSMContext) -> None:
    host = (message.text or "").strip()
    if not host:
        await message.answer("Send a non-empty IP or hostname.")
        return
    await state.update_data(host=host)
    await state.set_state(AddServer.password)
    await message.answer(
        "Step 2/2: send the SSH password.\n"
        "I will delete your message immediately after reading it."
    )


@router.message(AddServer.password, F.text)
async def add_step_password(message: Message, state: FSMContext) -> None:
    password = message.text or ""
    await _delete_message(message)
    if not password.strip():
        await message.answer("Password cannot be empty. Send /add_server to retry.")
        await state.clear()
        return
    await state.update_data(password=password)
    await _finalize_add_server(message, state)


async def _finalize_add_server(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    data = await state.get_data()
    await state.clear()
    host = str(data.get("host") or "")
    password = str(data.get("password") or "")
    if not host or not password:
        await message.answer("Session expired. Run /add_server again.")
        return

    status_msg = await message.answer(
        f"Queued install for <b>{escape(host)}</b>…", parse_mode="HTML"
    )
    try:
        result = await manager_client.create_server(
            host=host,
            login=DEFAULT_SSH_USER,
            password=password,
            ssh_port=DEFAULT_SSH_PORT,
            label=None,
        )
    except httpx.HTTPError as exc:
        await status_msg.edit_text(f"Manager call failed: {exc}")
        return
    job_id = str(result.get("jobId") or "")
    server_id = str(result.get("serverId") or "")
    if not job_id:
        await status_msg.edit_text("Manager did not return a jobId.")
        return

    last_render = ""
    deadline = asyncio.get_event_loop().time() + 60 * 25  # 25 minutes
    while asyncio.get_event_loop().time() < deadline:
        try:
            job = await manager_client.get_install_job(job_id)
        except httpx.HTTPError as exc:
            await status_msg.edit_text(f"Manager call failed: {exc}")
            return
        status = str(job.get("status") or "unknown")
        progress = str(job.get("progress") or "")
        text = (
            f"<b>install</b> {escape(host)}\n"
            f"server: <code>{escape(server_id)}</code>\n"
            f"job: <code>{escape(job_id)}</code>\n"
            f"status: <b>{escape(status)}</b>\n"
            f"progress: <code>{escape(progress)[:200]}</code>"
        )
        if text != last_render:
            with contextlib.suppress(Exception):
                await status_msg.edit_text(text, parse_mode="HTML")
            last_render = text
        if status in ("done", "error"):
            break
        await asyncio.sleep(3)
    else:
        await status_msg.edit_text("Install still running after 25 minutes; check /list_servers.")
        return

    if status == "error":
        error = escape(str(job.get("error") or "unknown"))
        await message.answer(f"Install failed: <code>{error}</code>", parse_mode="HTML")
        return

    panel_url = job.get("panelUrl") or "<unset>"
    panel_user = job.get("panelUser") or "<unset>"
    panel_password = job.get("panelPassword") or "<unset>"
    await message.answer(
        "Install complete. Save these one-time credentials:\n"
        f"panel: <code>{escape(str(panel_url))}</code>\n"
        f"login: <code>{escape(str(panel_user))}</code>\n"
        f"password: <code>{escape(str(panel_password))}</code>",
        parse_mode="HTML",
    )


@router.message(Command("list_servers"))
async def cmd_list_servers(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    try:
        servers = await manager_client.list_servers()
    except httpx.HTTPError as exc:
        await message.answer(f"Manager call failed: {exc}")
        return
    if not servers:
        await message.answer("No servers yet. Run /add_server.")
        return
    lines = []
    for server in servers:
        lines.append(
            f"<code>{escape(str(server.get('id')))}</code> "
            f"{escape(str(server.get('host')))} "
            f"[{escape(str(server.get('status')))}] "
            f"clients={server.get('clientCount', 0)}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("disable_server"))
async def cmd_disable_server(message: Message, command: CommandObject) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    server_id = (command.args or "").strip()
    if not server_id:
        await message.answer("Usage: /disable_server <server_id>")
        return
    try:
        await manager_client.disable_server(server_id)
    except httpx.HTTPError as exc:
        await message.answer(f"Manager call failed: {exc}")
        return
    await message.answer(f"Disabled {server_id}.")


@router.message(Command("enable_server"))
async def cmd_enable_server(message: Message, command: CommandObject) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    server_id = (command.args or "").strip()
    if not server_id:
        await message.answer("Usage: /enable_server <server_id>")
        return
    try:
        await manager_client.enable_server(server_id)
    except httpx.HTTPError as exc:
        await message.answer(f"Manager call failed: {exc}")
        return
    await message.answer(f"Enabled {server_id}.")
