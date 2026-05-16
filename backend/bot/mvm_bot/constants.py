from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
MENU_BANNER_PATH = BOT_DIR / "assets" / "telegram_menu_banner.png"
TRIAL_DAYS = 1
REFERRAL_BONUS_DAYS = 3
TRIAL_FIELDS = {
    "tg": "isTelegramTrialActivated",
    "apple": "isAppleTrialActivated",
    "vk": "isVkTrialActivated",
}

CONNECT_REDIRECT_ORIGIN = "https://front-redirect.vercel.app"

SUPPORT_URL = "https://t.me/MVM_Support"
VK_SUPPORT_URL = "https://vk.ru/id1088965138"

PRIVACY_POLICY_URL = "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
TERMS_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"

SUBSCRIPTION_PLANS: dict[str, dict] = {
    "plan_30": {
        "days": 30,
        "stars": 100,
        "label": "30 дней",
        "rub": 50,
        "crypto_usd": 3.39,
    },
    "plan_90": {
        "days": 90,
        "stars": 230,
        "label": "90 дней",
        "rub": 150,
        "crypto_usd": 6.34,
    },
}
