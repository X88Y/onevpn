from aiogram import Router  # type: ignore[import-not-found]

from mvm_bot.handlers.auth import router as auth_router
from mvm_bot.handlers.cabinet import router as cabinet_router

router = Router()
router.include_router(cabinet_router)
router.include_router(auth_router)
