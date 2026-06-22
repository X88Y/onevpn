import re


PROMO_CANDIDATE_RE = re.compile(r"^[A-Z0-9_-]{4,32}$")


def extract_promo_candidate(raw_text: str) -> tuple[str | None, bool]:
    text = raw_text.strip()
    if not text:
        return None, False

    lowered = text.lower()
    explicit_prefix = lowered.startswith("promo_") or lowered.startswith("promo ")
    if explicit_prefix:
        candidate = text[6:].strip().upper()
    else:
        candidate = text.upper()

    if not PROMO_CANDIDATE_RE.fullmatch(candidate):
        return None, explicit_prefix
    return candidate, explicit_prefix


def promo_multiplier(
    promo_activated: bool,
    promo_discount: object | None = None,
    default_discount: float = 0.0,
) -> float:
    if not promo_activated:
        return 1.0
    try:
        discount = float(promo_discount)
    except (TypeError, ValueError):
        discount = default_discount
    if 1 < discount <= 100:
        discount /= 100.0
    if not (0 < discount < 1):
        discount = default_discount
    return 1.0 - discount
