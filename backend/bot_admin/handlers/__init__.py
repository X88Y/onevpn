from aiogram import Router

from bot_admin.handlers.servers import router as servers_router
from bot_admin.handlers.vpn_keys import router as vpn_keys_router
from bot_admin.handlers.notifications import router as notifications_router
from bot_admin.handlers.statistics import router as statistics_router
from bot_admin.handlers.group_statistics import router as group_statistics_router
from bot_admin.handlers.promocodes import router as promocodes_router

router = Router()
router.include_router(servers_router)
router.include_router(vpn_keys_router)
router.include_router(notifications_router)
router.include_router(statistics_router)
router.include_router(group_statistics_router)
router.include_router(promocodes_router)
