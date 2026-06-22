from aiogram import Router  # type: ignore[import-not-found]

from mvm_bot.handlers.cabinet_devices import router as devices_router
from mvm_bot.handlers.cabinet_entry import router as entry_router
from mvm_bot.handlers.cabinet_payments import router as payments_router
from mvm_bot.handlers.cabinet_referrals import router as referrals_router
from mvm_bot.handlers.cabinet_support import router as support_router

router = Router()
router.include_router(entry_router)
router.include_router(payments_router)
router.include_router(devices_router)
router.include_router(support_router)
router.include_router(referrals_router)
