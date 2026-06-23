from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
MENU_BANNER_PATH = BOT_DIR / "assets" / "telegram_menu_banner.png"
MENU_BANNER_PATH_VK = BOT_DIR / "assets" / "vk_menu_banner.png"
MANUAL_DIR = BOT_DIR / "assets" / "manual"

TRIAL_DAYS = 4
REFERRAL_BONUS_DAYS = 7
REFERRAL_PURCHASE_BONUS_DAYS = 15
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
VK_PRIVACY_POLICY_URL = "https://vk.com/@mvmvpn-politika-konfidencialnosti"
VK_TERMS_URL = "https://vk.com/@mvmvpn-polzovatelskoe-soglashenie"

SITE_LINKS = [
    'mvmvpn.vercel.app',
    'мвм-скорость.рф',
]

PREMIUM_EXTERNAL_SQUAD_UUID = "d997add1-ecf9-43aa-874c-f235426ffef0"
PREMIUM_INTERNAL_SQUAD_UUID = "c2b488c4-2509-476c-923f-6620570ee3cc"

# PRICE HERE
SUBSCRIPTION_PLANS: dict[str, dict] = {
    "std_30": {
        "days": 30,
        "stars": 103,
        "label": "30 дней",
        "rub": 99,
        "tier": "standart",
        "emoji": "🤩",
        "tier_label": "Standart",
    },
    "std_90": {
        "days": 90,
        "stars": 312,
        "label": "90 дней",
        "rub": 299,
        "tier": "standart",
        "emoji": "🤩",
        "tier_label": "Standart",
    },
    "prem_30": {
        "days": 30,
        "stars": 291,
        "label": "30 дней",
        "rub": 279,
        "tier": "premium",
        "emoji": "💎",
        "tier_label": "Premium",
    },
    "prem_90": {
        "days": 90,
        "stars": 854,
        "label": "90 дней",
        "rub": 819,
        "tier": "premium",
        "emoji": "💎",
        "tier_label": "Premium",
    },
}

def is_premium_plan(plan_key: str) -> bool:
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    return plan is not None and plan.get("tier") == "premium"
