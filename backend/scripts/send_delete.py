import sys
import os
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
import aiohttp

VK_BOT_TOKENS="vk1.a.4-nDv62Wbzhd8cyzenM6GWH31OAIqejV4Q78yBX6d5D2MQvdMq-kYxp-Rl2gUTzX10fIOFim_YhNgsYs5hS2qivy7W5UgVtwhZJjOxB9FIaK-VWZc9SObNPvctdwGWrjJDDCLBwPrAMAdsZ3qdWLdHtAO6X735ad6hozBl9eJaX_SLzzf8jboIFas75_0Rg2EgYkdsxvyzgqI7jNq2ud3Q,vk1.a.yCG8RlbvAvh9p8fRZxiWb8PIsw3fI3P5KQlHEA7jCMxKZPRYJBVdNdehSZMXwW83tz6uPy9Cvkkcyr-Z88it9J1OnhpIPa6YORUO-nnp__xLPKfdXtzymOkxBYwD9r_uX_QDwZaeto8aY93GQecShAjHjmANvelDDKrKWB7T-z9d1LmcNK_2r4TCP1dTNagi7ekfyxrui3u0kYgFp-WV8A,vk1.a.J-qP_B4VFuvCb63pN3WsbtLHeQuMwULBtE1jjIYcSPCUbzPxTK40f4w0hRoQAz5Fde1suVTaxlJeif0Ik5tuqvLfrqIuNN9gzMVwbvePxL2qM7az43Q-K43jOjnFzPvxslhoQFEJd_TujzvKDG9CZMrdL6iWV-pTj5QseHIkS5DRIIJg1oSuK-bO6K1kEa-2QuNdiLTEuahjay5C7Oiuzg,vk1.a.Qb3E7UwlrezOaQ_2AWjTwReYFhFKIbgTRXv-jaamJB7gAFr0jpiVzGGFq-ovrlF-z2GrnAg8Z9-jWZ3kzTXjja4Ua0BhP0WdY-uCiGcMFXJwJcT9R1SaMWLM4Ypl6yLTYAnb92n5yyYHbH05C47vLx-TRSdv6IQ8-SoEINdt2qi9WjowkQwInJP7rmUd33iIWlmhMo3Dc6dXP4AHUCZi9w,vk1.a.7vXl0_XMqSO5K3gtgHdRPfyef9CKhpxGM5smZnMUJ9lk47i1ekyeAQDaVUX3cmsk13alGGdER3qNd8Sodq4JwbFw7mr17cv47MG5zvB2mpxTUuDL0ZWMbw6QgUfM-I4uz2OhbectnzaRybxg5PS583skDvUrfIPbjWd8UKZZjpGmNMeLv5H9YXpZzXcuApnuqm2c3eSg7fL8NQU1phem-g,vk1.a.iDPTGrW2wgpg6qsm-82dRYiBpX5S_7m4Z1qIxjPhK5GC4uKJnfe7beksq3m4LhNgYdflm1ex-C-r4qaajzq6LVStu8QURL_rryOLot7qWgnkSgnGM3L9CS5EnenpN0jvIvGnPMcb1hJSuPrBARF1nvshjplSQd-t6kwmKhUcm1d7mUzc-0t95rieuqoKn1tKPpF5n3CC-3HnDzLyQ8gl8A,vk1.a.xiQBLVtxpiDUJ7YpezJ_dmdv3cK1DjKGDqWTfabHUBsLKFWPr_6u-9Jeow1Hp289GOcejd53dMxgk98DgpdZJFbxX6i5BeeHyyEso-PwTDAYZf9s1F06j3EC8YWbrKE3-BkB6BkZ-6ne5ONmiFsFl02ds0iRrGGZZzP5lDomkic9aqvrBZTnuzXhwAujKKSsNr6SoZTPj7fMh4vq5ocDqg,vk1.a.eeyFYd8Qds6ZrM0TCi4zXgADqBd5lDa7CpLm-5f_XA9Af3Vs57lvxcQzehfcTqzQfX-K4-LGgfxi_M2FCN7wLHwvRdfC99tkQZTMApxg66dhpcjdDXWqlZ7a_1IK0VgSfA2dRDqi7XH0qfTGahDchIKjPO_HUWFesyXLOUGcum2x8msDZvIwFME-dyUOgjuErfZiL4z9Us07lrC05hVeGQ,vk1.a.FAgIkQeYkBYfLrE0oCwdLMWhc_DbuFhth-aexjg2Oejk9nAGZoHSqu_APJgsK7leKzhhW1zBqmE1XYunwxDaf5uPgD62rcMCgLMjgGqjaCQvEz7uaiDLBjpK8ynmslCq5DZzKfbgjtkdmHTbr3QQ9sGL5UoSv-_bLTGxNs30u_pVeW_jPhWjxGGaRGGMG6eEXV3mukhA8Otu7RbeKuHQng,vk1.a.fZTplLMkpa_ntcMOsYogZA4f5UL2ogBtk_AqYnOeYvrf6vIvg39u800wgb3wwsGPdAlX76V7NIwSijxJtfJwTSg2lW4U7La0YUU8y-6J9fIP_D32yBeJpNYONVsfa2H_RK8Bn8Y646gJsakVSaXjAmzV32R-_Umx1OZ2O1NzIkSvXGUHx_n-xgDawwKcI20SqJguZYK3IuJ3IkjJzCEg2g,vk1.a.kwoYMfIQ6zagpNp2BHfl6yIdvFjegwP1vXbkVRxmTK0RIowVQD-HXFmiG9iWnhCc_azpiCAd0w0X60GwnlgZUQXYkrmpknvhhfNWPNzNR80YIUiuJG9lGNjHxMmWwCcqbwV9eMJlN1RatAXLnkh66jOFPtExNPAHK8nLa56IwxITnBvoN0JMheZ67uegGPVAo_Tbm1xoGgFANRvcbt3mbg,vk1.a.ZgHd8-u7zGyPbMvzztgga3jHqaJWBQV-o8kHHO0IhkIvEAlNjPbD5fzO4K8V-rNgB2nzVzp7QlBkj__vgqmAtxef4iJis59yvyjNoAapP3mHzBmR35sYIUj34oZlBwI4Y8g2qQGSsasAqhjGSad6Epcl2mAJX8aWKlnbaknOPn8txXe6FXA0Iz4XIDkxyUkGd00ojHwbJSFMz1emE-f5sQ"
tokens = VK_BOT_TOKENS.split(',')

text= '''
Уважаемые пользователи🫶

Мы наконец починили работу серверов подключения к белых спискам🥳
Это был тяжелый бой с блокировками наших серверов, но мы выстояли и сейчас все работает🫡

В качестве компенсации за неудобства в ближайшее время вам в подписку начислятся все дни, когда обходы не работали! 

❗️Также хотим напомнить, что с 23 июня поднимутся тарифы на подписку. Сейчас очень низкая цена и мы оставляем возможность купить подписку сразу на несколько месяцев🥰

И в завершении - наши группы в ВК постоянно блокируют, поэтому что бы не терять связь, подписывайтесь на телеграмм канал: https://t.me/mvm_vpn

Спасибо, что выбираете наш MVM VPN и приглашаете друзей по реферальной системе ⚡️
'''

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("send_delete")

# Directory for progress files
sended_dir = Path(__file__).resolve().parent / "sended"
sended_dir.mkdir(parents=True, exist_ok=True)

# Parse simple command line options
DRY_RUN = "--dry-run" in sys.argv
LIMIT = None
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

async def get_group_info(session: aiohttp.ClientSession, token: str) -> dict:
    params = {
        "access_token": token,
        "v": "5.231"
    }
    try:
        async with session.post("https://api.vk.com/method/groups.getById", data=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error(f"HTTP error {resp.status} in groups.getById: {body}")
                return None
            data = await resp.json()
            if "error" in data:
                logger.error(f"VK API error in groups.getById: {data['error']}")
                return None
            groups = data.get("response", {}).get("groups", [])
            if not groups:
                logger.error(f"No groups returned in groups.getById response: {data}")
                return None
            return groups[0]
    except Exception as e:
        logger.exception(f"Exception during groups.getById: {e}")
        return None

async def send_vk_message(
    session: aiohttp.ClientSession,
    token: str,
    peer_id: int,
    message: str,
    group_logger: logging.Logger
) -> bool:
    params = {
        "peer_id": peer_id,
        "message": message,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000) + peer_id % 1000),
        "access_token": token,
        "v": "5.231"
    }
    try:
        async with session.post("https://api.vk.com/method/messages.send", data=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                group_logger.error(f"HTTP error {resp.status} sending to {peer_id}: {body}")
                return False
            data = await resp.json()
            if "error" in data:
                err = data["error"]
                group_logger.error(f"VK API error sending to {peer_id}: {err.get('error_msg')} (code {err.get('error_code')})")
                return False
            return True
    except Exception as e:
        group_logger.exception(f"Exception sending to {peer_id}: {e}")
        return False

async def process_group_mailing(token: str, session: aiohttp.ClientSession):
    group_info = await get_group_info(session, token)
    if not group_info:
        logger.error(f"Could not retrieve group info for token {token[:10]}... Skipping.")
        return
    
    group_id = group_info["id"]
    group_name = group_info.get("name", f"Group {group_id}")
    group_logger = logging.getLogger(f"Group-{group_id}")
    group_logger.info(f"Starting mailing for group: '{group_name}'")
    
    sended_file = sended_dir / f"{group_id}.txt"
    sent_ids = set()
    if sended_file.exists():
        try:
            with open(sended_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            sent_ids.add(int(line))
                        except ValueError:
                            group_logger.warning(f"Skipping invalid line in {sended_file.name}: {line}")
            group_logger.info(f"Loaded {len(sent_ids)} already processed user IDs from {sended_file.name}")
        except Exception as e:
            group_logger.error(f"Error reading {sended_file.name}: {e}")
            
    success_count = 0
    fail_count = 0
    total_sent_this_run = 0
    
    sended_file.parent.mkdir(parents=True, exist_ok=True)
    
    offset = 0
    page_size = 200
    
    while True:
        if LIMIT and total_sent_this_run >= LIMIT:
            group_logger.info(f"Reached global limit of {LIMIT} users. Stopping group mailing.")
            break
            
        params = {
            "access_token": token,
            "v": "5.231",
            "offset": offset,
            "count": page_size,
            "extended": 0
        }
        
        group_logger.info(f"Fetching conversations (offset={offset})...")
        try:
            async with session.post("https://api.vk.com/method/messages.getConversations", data=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    group_logger.error(f"HTTP error {resp.status} in messages.getConversations: {body}")
                    break
                data = await resp.json()
                if "error" in data:
                    group_logger.error(f"VK API error in messages.getConversations: {data['error']}")
                    break
                
                response_obj = data.get("response", {})
                items = response_obj.get("items", [])
                if not items:
                    group_logger.info("No more conversations found on this page.")
                    break
                
                # Extract valid peer_ids from this page
                page_users = []
                for item in items:
                    conv = item.get("conversation", {})
                    peer = conv.get("peer", {})
                    peer_id = peer.get("id")
                    peer_type = peer.get("type")
                    
                    if peer_type == "user" and peer_id and peer_id > 0:
                        page_users.append(peer_id)
                
                # Filter out already sent users
                users_to_send = [u for u in page_users if int(u) not in sent_ids]
                group_logger.info(f"Fetched {len(items)} items. Found {len(page_users)} user(s) on page, {len(users_to_send)} need messaging.")
                
                # Send to users of the current page immediately
                for idx, peer_id in enumerate(users_to_send, 1):
                    if LIMIT and total_sent_this_run >= LIMIT:
                        group_logger.info(f"Reached global limit of {LIMIT} users during page processing.")
                        break
                        
                    if peer_id in sent_ids:
                        continue
                        
                    if DRY_RUN:
                        group_logger.info(f"[Dry Run] Would send message to user {peer_id}")
                        success_count += 1
                        total_sent_this_run += 1
                        sent_ids.add(peer_id)
                    else:
                        group_logger.info(f"Sending message to user {peer_id}...")
                        success = await send_vk_message(session, token, peer_id, text, group_logger)
                        if success:
                            success_count += 1
                            total_sent_this_run += 1
                            try:
                                with open(sended_file, "a") as f:
                                    f.write(f"{peer_id}\n")
                                sent_ids.add(peer_id)
                            except Exception as e:
                                group_logger.error(f"Failed to save user {peer_id} to {sended_file.name}: {e}")
                        else:
                            fail_count += 1
                        
                        await asyncio.sleep(0.34)
                
                # If we received fewer items than page_size, we are on the last page
                if len(items) < page_size:
                    group_logger.info("Fewer items than page size returned. Reached the end of conversations.")
                    break
                    
        except Exception as e:
            group_logger.exception(f"Exception during page processing: {e}")
            break
            
        offset += page_size
        await asyncio.sleep(0.34)
        
    group_logger.info(f"Mailing finished. Sent successfully: {success_count}, Failed: {fail_count}")

async def main():
    if DRY_RUN:
        logger.info("=== RUNNING IN DRY RUN MODE ===")
    if LIMIT:
        logger.info(f"=== LIMIT SET TO {LIMIT} USERS PER TOKEN ===")
        
    async with aiohttp.ClientSession() as session:
        tasks = [process_group_mailing(token, session) for token in tokens]
        await asyncio.gather(*tasks)
    logger.info("All group mailings completed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting.")
        sys.exit(0)