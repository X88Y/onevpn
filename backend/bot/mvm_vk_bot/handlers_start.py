from vkbottle import Keyboard, Text

from mvm_bot.promo_utils import extract_promo_candidate
from mvm_bot.user_service import apply_promo_code_vk, apply_referral_code_vk, save_vk_user
from mvm_bot.user_service.promo import check_promo_code_validity
from mvm_vk_bot.menu import plan_selection_keyboard_json, send_main_menu
from mvm_vk_bot.profile import fetch_vk_profile


async def handle_private_message(message) -> None:
    text = (message.text or "").strip()
    profile = await fetch_vk_profile(message.ctx_api, message.from_id)

    if text == "Профиль":
        _, data = await save_vk_user(profile, group_id=message.group_id)
        await send_main_menu(message, data)
        return

    if text.startswith("ref_"):
        code = text[4:]
        _, data = await save_vk_user(profile, group_id=message.group_id)
        success, msg = await apply_referral_code_vk(profile, code)
        await message.answer(message=f"{'✅' if success else '❌'} {msg}")

        kb = Keyboard(one_time=False, inline=False)
        kb.add(Text("Профиль"))
        await message.answer(
            message="Добро пожаловать в MVM VPN! 🚀\n\nНажмите кнопку «Профиль» ниже для перехода в личный кабинет 👇",
            keyboard=kb.get_json(),
        )
        await send_main_menu(message, data)
        return

    candidate, explicit_prefix = extract_promo_candidate(text)
    if candidate is not None:
        is_valid, _ = await check_promo_code_validity(candidate)
        if is_valid:
            await save_vk_user(profile, group_id=message.group_id)
            success, msg = await apply_promo_code_vk(profile, candidate)
            if success:
                _, updated_data = await save_vk_user(profile, group_id=message.group_id)
                promo_activated = updated_data.get("promoActivated", False)
                await message.answer(
                    message=msg,
                    keyboard=plan_selection_keyboard_json(
                        promo_activated=promo_activated,
                        promo_discount=updated_data.get("promoDiscount"),
                    ),
                )
            else:
                await message.answer(message=f"❌ {msg}")
            return
        if explicit_prefix:
            await message.answer(message="❌ Неверный или неактивный промокод.")
            return

    _, data = await save_vk_user(profile, group_id=message.group_id)

    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Профиль"))
    await message.answer(
        message="Добро пожаловать в MVM VPN! 🚀\n\nНажмите кнопку «Профиль» ниже для перехода в личный кабинет 👇",
        keyboard=kb.get_json(),
    )
    await send_main_menu(message, data)
