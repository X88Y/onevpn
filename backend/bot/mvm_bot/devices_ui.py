def device_limit_for_tier(tier: object) -> int:
    return 7 if tier == "premium" else 1


def device_display_name(device: dict) -> str:
    model = device.get("deviceModel") or device.get("device_model")
    platform = device.get("platform")
    os_version = device.get("osVersion") or device.get("os_version")
    parts: list[str] = []
    if model:
        parts.append(str(model))
    if platform:
        parts.append(str(platform))
    if os_version:
        parts.append(str(os_version))
    return " ".join(parts) if parts else str(device.get("hwid") or "Unknown Device")
