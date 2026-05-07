from aiogram import Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.filters import Command  # type: ignore[import-not-found]
from aiogram.types import Message  # type: ignore[import-not-found]
from aiogram.utils.markdown import code  # type: ignore[import-not-found]
from aiogram.utils.text_decorations import markdown_decoration  # type: ignore[import-not-found]

from mvm_bot.jwt_auth import sign_tg_auth_jwt
from mvm_bot.user_service import save_telegram_user

router = Router()

