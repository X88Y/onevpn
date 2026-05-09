import asyncio
import contextlib
import logging
from html import escape
from typing import Optional

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot_admin.config import admin_telegram_ids
from bot_admin import manager_client

logger = logging.getLogger(__name__)
router = Router(name="servers")

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "root"

STATUS_EMOJIS = {
    "healthy": "✅",
    "provisioning": "🔄",
    "disabled": "❌",
    "error": "⚠️",
    "unknown": "❓",
}


class ServerPagination(CallbackData, prefix="srv_pg"):
    page: int


class ServerAction(CallbackData, prefix="srv_act"):
    action: str  # "disable"
    server_id: str
    page: int


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


@router.message(Command("list_servers", "list_server"))
async def cmd_list_servers(message: Message) -> None:
    await _show_server_list(message, page=1)


async def _show_server_list(event: Message | CallbackQuery, page: int = 1) -> None:
    user_id = event.from_user.id if event.from_user else None
    if not _is_admin(user_id):
        if isinstance(event, Message):
            await event.answer("Access denied.")
        else:
            await event.answer("Access denied.", show_alert=True)
        return

    limit = 10
    try:
        data = await manager_client.list_servers(page=page, limit=limit)
    except httpx.HTTPError as exc:
        msg = f"Manager call failed: {exc}"
        if isinstance(event, Message):
            await event.answer(msg)
        else:
            await event.answer(msg, show_alert=True)
        return

    servers = data.get("servers", [])
    total = data.get("total", 0)

    if not servers and page == 1:
        if isinstance(event, Message):
            await event.answer("No servers yet. Run /add_server.")
        else:
            await event.answer("No servers found.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()

    for s in servers:
        status = s.get("status", "unknown")
        emoji = STATUS_EMOJIS.get(status, STATUS_EMOJIS["unknown"])
        host = s.get("host", "unknown")
        sid = s.get("id", "")
        label = s.get("label")
        display_name = f"{label} ({host})" if label else host
        
        # Action is disable by default. If already disabled, turn to error.
        action = "error" if status == "disabled" else "disable"
        
        button_text = f"{emoji} {display_name}"
        builder.row(InlineKeyboardButton(
            text=button_text,
            callback_data=ServerAction(action=action, server_id=sid, page=page).pack()
        ))

    # Pagination row
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Prev",
            callback_data=ServerPagination(page=page - 1).pack()
        ))
    if page * limit < total:
        nav_buttons.append(InlineKeyboardButton(
            text="Next ➡️",
            callback_data=ServerPagination(page=page + 1).pack()
        ))

    if nav_buttons:
        builder.row(*nav_buttons)

    text = (
        f"<b>Servers List (Page {page})</b>\n"
        f"Total servers: {total}\n\n"
        f"<i>Click a server to disable it (or mark as error if already disabled).</i>"
    )

    if isinstance(event, Message):
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        with contextlib.suppress(Exception):
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(ServerPagination.filter())
async def on_server_pagination(callback: CallbackQuery, callback_data: ServerPagination):
    await _show_server_list(callback, page=callback_data.page)
    await callback.answer()


@router.callback_query(ServerAction.filter(F.action == "disable"))
async def on_disable_server(callback: CallbackQuery, callback_data: ServerAction):
    user_id = callback.from_user.id if callback.from_user else None
    if not _is_admin(user_id):
        await callback.answer("Access denied.", show_alert=True)
        return

    try:
        await manager_client.disable_server(callback_data.server_id)
        await callback.answer(f"✅ Server {callback_data.server_id} has been disabled.", show_alert=True)
        # Refresh the current page to show updated status
        await _show_server_list(callback, page=callback_data.page)
    except httpx.HTTPError as exc:
        await callback.answer(f"❌ Failed to disable server: {exc}", show_alert=True)


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
@router.callback_query(ServerAction.filter(F.action == "error"))
async def on_error_server(callback: CallbackQuery, callback_data: ServerAction):
    user_id = callback.from_user.id if callback.from_user else None
    if not _is_admin(user_id):
        await callback.answer("Access denied.", show_alert=True)
        return

    try:
        await manager_client.set_server_error(callback_data.server_id)
        await callback.answer(f"⚠️ Server {callback_data.server_id} marked as error.", show_alert=True)
        # Refresh the current page
        await _show_server_list(callback, page=callback_data.page)
    except httpx.HTTPError as exc:
        await callback.answer(f"❌ Failed to mark as error: {exc}", show_alert=True)
