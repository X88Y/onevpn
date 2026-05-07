from aiogram import Router

from bot_admin.handlers.servers import router as servers_router
from bot_admin.handlers.vpn_keys import router as vpn_keys_router

router = Router()
router.include_router(servers_router)
router.include_router(vpn_keys_router)
