from typing import TYPE_CHECKING

from mvm_bot.user_service import VkProfile

if TYPE_CHECKING:
    from vkbottle.api import ABCAPI


async def fetch_vk_profile(api: "ABCAPI", user_id: int) -> VkProfile:
    users = await api.users.get(user_ids=[user_id], fields=["domain"])
    u = users[0]
    domain = getattr(u, "domain", None)
    if domain == "":
        domain = None
    return VkProfile(
        id=int(u.id),
        first_name=u.first_name or "",
        last_name=u.last_name,
        screen_name=domain,
    )
