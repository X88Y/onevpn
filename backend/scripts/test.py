import sys
from pathlib import Path
import os
# ---------------------------------------------------------------------------
# 1. Discover bot directory and load .env BEFORE any imports that read env vars
# ---------------------------------------------------------------------------
_script_dir = Path(__file__).resolve().parent

# Try to locate the bot/ folder (works whether this file lives in backend/, backend/bot/ or backend/scripts/)
if (_script_dir / "bot" / "mvm_bot").is_dir():
    BOT_DIR = _script_dir / "bot"
elif (_script_dir / "mvm_bot").is_dir():
    BOT_DIR = _script_dir
elif (_script_dir.parent / "bot" / "mvm_bot").is_dir():
    BOT_DIR = _script_dir.parent / "bot"
else:
    raise RuntimeError(
        "Cannot find bot/ directory. Place this file in backend/, backend/bot/, or backend/scripts/"
    )

sys.path.insert(0, str(BOT_DIR))

from dotenv import load_dotenv

_env_path = BOT_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    print(f"Loaded .env from {_env_path}")
else:
    print(f"Warning: {_env_path} not found, relying on existing environment variables")

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKENS", "").split(",")[0].strip()  # Use the first token if multiple are provided
"""
VK Wall Post Deleter
Удаляет все посты со стены группы или пользователя через VK API (vk_bottle / vk_api).

Установка зависимостей:
    pip install vk-api

Использование:
    python test.py

Или передать параметры через аргументы:
    python test.py --token YOUR_TOKEN --group_id 123456789
    python test.py --cookies "remixsid=...; ..." --user_id 123456789
"""

import time
import argparse
import vk_api
import requests
import re

# ─── Настройки ────────────────────────────────────────────────────────────────

DEFAULT_TOKEN    = VK_BOT_TOKEN  # токен группы или пользователя
DEFAULT_GROUP_ID = 0                     # оставь 0 — будет определён автоматически из токена

REQUESTS_PER_SECOND = 5   # VK разрешает до 3 запросов/сек
BATCH_SIZE          = 100  # сколько постов получать за раз (макс. 100)

# ──────────────────────────────────────────────────────────────────────────────


def parse_cookies(cookie_string: str) -> dict:
    """Parse a cookie string into a dictionary."""
    cookies = {}
    for item in cookie_string.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key] = value
    return cookies


def get_user_token_from_cookies(cookies: dict, scope: str = "wall,offline") -> str:
    """
    Extract a user access token from VK web session cookies via implicit OAuth flow.
    Since the user is already logged in (valid remixsid), VK redirects immediately
    with the access token in the URL fragment.
    """
    sess = requests.Session()
    for name, value in cookies.items():
        sess.cookies.set(name, value, domain=".vk.com")
        sess.cookies.set(name, value, domain="vk.com")

    # Try common VK app IDs used for implicit flow
    for client_id in ("2274003", "3140623", "6121396"):
        auth_url = (
            "https://oauth.vk.com/authorize"
            f"?client_id={client_id}"
            "&redirect_uri=https://oauth.vk.com/blank.html"
            "&response_type=token"
            f"&scope={scope}"
            "&v=5.199"
        )
        resp = sess.get(auth_url, allow_redirects=True)

        # Token may be in the final redirect URL
        token_match = re.search(r"access_token=([^&]+)", resp.url)
        if not token_match:
            # Or embedded in the response HTML/JS
            token_match = re.search(r"access_token[=:]([^&\"'\s]+)", resp.text)

        if token_match:
            token = token_match.group(1)
            print(f"  Успешно получен user token (client_id={client_id})")
            return token

    raise RuntimeError(
        "Не удалось извлечь access token из cookies. "
        "Возможно, cookies просрочены или требуется дополнительная авторизация."
    )


def resolve_group_id(vk) -> int:
    """Определить ID группы из токена.
    Работает только для токенов, выданных от имени сообщества."""
    try:
        response = vk.groups.getById()
        if response:
            group_id = response[0]["id"]
            name = response[0].get("name", "")
            print(f"Группа определена автоматически: [{group_id}] {name}")
            return group_id
    except vk_api.exceptions.ApiError:
        pass

    raise SystemExit(
        "❌  Не удалось определить ID группы из токена.\n"
        "    Укажите его вручную: --group_id 123456789\n"
        "    (Токен должен быть выдан от имени сообщества, а не пользователя)"
    )


def resolve_user_id(vk) -> int:
    """Определить ID пользователя из user токена."""
    try:
        response = vk.users.get()
        if response:
            user_id = response[0]["id"]
            name = f"{response[0].get('first_name', '')} {response[0].get('last_name', '')}".strip()
            print(f"Пользователь определён автоматически: [{user_id}] {name}")
            return user_id
    except vk_api.exceptions.ApiError as e:
        raise SystemExit(f"❌  Не удалось определить ID пользователя: {e}")


def get_all_post_ids(vk, owner_id: int) -> list[int]:
    """Получить ID всех постов со стены."""
    post_ids = []
    offset = 0

    print("Получаем список постов...")
    while True:
        start_time = time.time()
        try:
            response = vk.wall.get(
                owner_id=owner_id,
                count=BATCH_SIZE,
                offset=offset,
                filter="owner",   # только посты владельца (не чужие)
            )
        except vk_api.exceptions.ApiError as e:
            if e.code == 9:
                print("Flood control detected on wall.get. Sleeping for 5 seconds...")
                time.sleep(5)
                continue
            raise

        items = response.get("items", [])
        if not items:
            break

        post_ids.extend(item["id"] for item in items)
        total = response.get("count", 0)
        # offset += len(items)
        print(f"  Загружено {len(post_ids)} / {total}")

        # if offset >= total:
        #     break

        # time.sleep(1 / REQUESTS_PER_SECOND)

        delete_posts(vk, owner_id, post_ids)
        total_time = time.time() - start_time
        print(f"  Удалено {len(items)} постов, продолжаем...\n осталось примерно {time.strftime('%H:%M:%S', time.gmtime((total / len(post_ids)) * total_time))} до конца")
        post_ids.clear()  # очищаем список после удаления, чтобы не держать в памяти
    # return post_ids


def delete_posts(vk, owner_id: int, post_ids: list[int]) -> None:
    """Удалить все переданные посты по одному."""
    total = len(post_ids)
    print(f"\nНачинаем удаление {total} постов...")

    for i, post_id in enumerate(post_ids, 1):
        retries = 5
        while retries > 0:
            try:
                vk.wall.delete(owner_id=owner_id, post_id=post_id)
                print(f"  [{i}/{total}] Удалён пост {post_id}")
                break
            except vk_api.exceptions.ApiError as e:
                if e.code == 9:  # Flood control
                    print(f"  [{i}/{total}] Flood control detected on wall.delete. Sleeping for 5 seconds before retry (retries left: {retries-1})...")
                    time.sleep(5)
                    retries -= 1
                else:
                    print(f"  [{i}/{total}] Ошибка при удалении поста {post_id}: {e}")
                    break
            except Exception as e:
                print(f"  [{i}/{total}] Непредвиденная ошибка при удалении поста {post_id}: {e}")
                break

        time.sleep(1 / REQUESTS_PER_SECOND)


def main():
    parser = argparse.ArgumentParser(description="Удалить все посты со стены VK-группы или пользователя")
    parser.add_argument("--token",    default=DEFAULT_TOKEN,    help="Access token (группы или пользователя)")
    parser.add_argument("--group_id", default=DEFAULT_GROUP_ID, type=int,
                        help="ID группы (без минуса)")
    parser.add_argument("--user_id",  default=0, type=int,
                        help="ID пользователя (для удаления со стены пользователя)")
    parser.add_argument("--cookies",  default=None,
                        help="Строка cookies VK для user-авторизации (или путь к файлу с cookies)")
    args = parser.parse_args()

    token = args.token
    owner_id = None

    # ── User authorization via cookies ──────────────────────────────────────
    if args.cookies:
        cookie_string = args.cookies
        # If --cookies points to an existing file, read its contents
        cookie_path = Path(cookie_string)
        if cookie_path.exists():
            cookie_string = cookie_path.read_text(encoding="utf-8").strip()

        print("Авторизация через cookies...")
        cookies = parse_cookies(cookie_string)
        if not cookies.get("remixsid"):
            print("  Предупреждение: remixsid не найден в cookies")

        token = get_user_token_from_cookies(cookies)

        session = vk_api.VkApi(token=token)
        vk = session.get_api()

        if args.user_id:
            owner_id = args.user_id
            print(f"Целевой пользователь (из аргумента): {owner_id}")
        else:
            owner_id = resolve_user_id(vk)

    # ── Token-based authorization (group or user token) ─────────────────────
    elif token and token != "YOUR_ACCESS_TOKEN":
        session = vk_api.VkApi(token=token)
        vk = session.get_api()

        if args.user_id:
            owner_id = args.user_id
        elif args.group_id:
            owner_id = -abs(args.group_id)
        else:
            # Try auto-detect user token first, then group token
            try:
                owner_id = resolve_user_id(vk)
            except SystemExit:
                # Not a user token — try group token
                try:
                    group_id = resolve_group_id(vk)
                    owner_id = -abs(group_id)
                except SystemExit:
                    raise SystemExit(
                        "❌  Не удалось определить тип токена.\n"
                        "    Убедитесь, что токен действителен, "
                        "или укажите --group_id / --user_id."
                    )
    else:
        raise SystemExit(
            "❌  Укажите способ авторизации:\n"
            "    --token YOUR_TOKEN   (токен группы или пользователя)\n"
            "    --cookies 'remixsid=...; ...'   (cookies для user-авторизации)"
        )

    if owner_id is None:
        raise SystemExit("❌  Не удалось определить owner_id. Укажите --group_id или --user_id.")

    # Verify the token can access wall.get before fetching all posts
    try:
        vk.wall.get(owner_id=owner_id, count=1)
    except vk_api.exceptions.ApiError as e:
        if e.code == 27:
            raise SystemExit(
                "❌  Групповой (community) токен не может использовать метод wall.get.\n"
                "    Для чтения и удаления постов требуется пользовательский токен с правом wall.\n\n"
                "    Решения:\n"
                "    1. Используйте --cookies 'remixsid=...' для авторизации через cookies VK\n"
                "    2. Укажите пользовательский токен через --token USER_TOKEN"
            )
        if e.code == 5:
            raise SystemExit(
                "❌  Токен просрочен или недействителен (error 5).\n"
                "    Обновите токен или используйте --cookies для получения нового."
            )
        if e.code == 15:
            raise SystemExit(
                "❌  Доступ к стене запрещён (error 15).\n"
                "    У пользователя нет прав на просмотр/удаление постов этой стены."
            )
        raise

    post_ids = get_all_post_ids(vk, owner_id)
    return 'ok'
    if not post_ids:
        print("Нет постов для удаления.")
        return

    print(f"\nНайдено постов: {len(post_ids)}")
    confirm = input("Удалить все посты? Это действие необратимо! (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Отменено.")
        return

    delete_posts(vk, owner_id, post_ids)
    print("\n✅  Готово! Все посты удалены.")


if __name__ == "__main__":
    main()
