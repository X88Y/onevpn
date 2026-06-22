from datetime import datetime, timedelta, timezone

import asyncio
import httpx

from mvm_bot.config import yoomoney_receiver, yoomoney_recurring_enabled, yoomoney_secret
from mvm_bot.constants import SUBSCRIPTION_PLANS
from mvm_bot.yoomoney import build_label


async def attempt_autocharge(
    user_id: str,
    plan_key: str,
    payment_method_id: str,
    provider: str,
    *,
    logger,
) -> bool:
    receiver = yoomoney_receiver()
    secret = yoomoney_secret()
    if not receiver or not secret:
        logger.error("Autocharge failed: receiver or secret not configured")
        return False

    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        logger.error("Autocharge failed: plan %s not found", plan_key)
        return False

    amount = plan["rub"]
    label = build_label(provider, user_id, plan_key)

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB",
        },
        "capture": True,
        "payment_method_id": payment_method_id,
        "description": f"Автопродление подписки MVMVpn ({plan['label']})",
        "metadata": {"label": label},
    }

    headers = {
        "Idempotence-Key": label,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                headers=headers,
                auth=(receiver, secret),
                timeout=15.0,
            )
            if response.status_code in (200, 201):
                data = response.json()
                status = data.get("status")
                if status == "succeeded":
                    logger.info("Autocharge succeeded for user %s via label %s", user_id, label)
                    return True
                logger.warning("Autocharge returned status %s for user %s", status, user_id)
                return False
            logger.error("Autocharge API request failed: %s %s", response.status_code, response.text)
            return False
    except Exception:
        logger.exception("Autocharge error for user %s", user_id)
        return False


def _should_attempt_from_last_attempt(last_attempt: object) -> bool:
    if not last_attempt:
        return True
    if hasattr(last_attempt, "timestamp"):
        last_attempt_dt = last_attempt
    else:
        try:
            last_attempt_dt = datetime.fromisoformat(str(last_attempt))
        except Exception:
            last_attempt_dt = None
    if not last_attempt_dt:
        return True
    return datetime.now(timezone.utc) - last_attempt_dt >= timedelta(hours=24)


async def maybe_handle_autocharge(
    *,
    snap,
    user_data: dict,
    tg_id: str | None,
    vk_id: str | None,
    notify_telegram,
    notify_vk,
    logger,
) -> bool:
    payment_method_id = user_data.get("yookassaPaymentMethodId")
    if not payment_method_id or not yoomoney_recurring_enabled():
        return False

    if not _should_attempt_from_last_attempt(user_data.get("yookassaLastChargeAttemptAt")):
        return True

    provider = "tg" if tg_id else "vk"
    uid = tg_id if tg_id else vk_id
    if not uid:
        return True
    plan_key = user_data.get("yookassaPlanKey") or "plan_30"

    ref = snap.reference
    await asyncio.to_thread(
        lambda r=ref, ts=datetime.now(timezone.utc): r.update({"yookassaLastChargeAttemptAt": ts})
    )

    success = await attempt_autocharge(
        user_id=uid,
        plan_key=plan_key,
        payment_method_id=payment_method_id,
        provider=provider,
        logger=logger,
    )
    if success:
        return True

    fail_text = (
        "⚠️ Автоматическое продление вашей подписки не удалось (например, недостаточно средств на карте).\n\n"
        "Пожалуйста, продлите подписку вручную в личном кабинете."
    )
    if tg_id:
        await notify_telegram(tg_id, fail_text)
    if vk_id:
        await notify_vk(vk_id, fail_text)
    return True
