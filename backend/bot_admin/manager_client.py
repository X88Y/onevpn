import httpx

from bot_admin.config import manager_api_key, manager_base_url


def _client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=manager_base_url(),
        headers={"X-API-Key": manager_api_key()},
        timeout=timeout,
    )


async def create_server(host: str, login: str, password: str, *, ssh_port: int = 22, label: str = None) -> dict:
    payload = {"host": host, "login": login, "password": password, "sshPort": ssh_port}
    if label:
        payload["label"] = label
    async with _client() as http:
        response = await http.post("/servers", json=payload)
        response.raise_for_status()
        return response.json()


async def get_install_job(job_id: str) -> dict:
    async with _client() as http:
        response = await http.get(f"/install_jobs/{job_id}")
        response.raise_for_status()
        return response.json()


async def list_servers() -> list[dict]:
    async with _client() as http:
        response = await http.get("/servers")
        response.raise_for_status()
        return list(response.json())


async def disable_server(server_id: str) -> dict:
    async with _client() as http:
        response = await http.post(f"/servers/{server_id}/disable")
        response.raise_for_status()
        return response.json()


async def enable_server(server_id: str) -> dict:
    async with _client() as http:
        response = await http.post(f"/servers/{server_id}/enable")
        response.raise_for_status()
        return response.json()


async def delete_server(server_id: str) -> dict:
    async with _client() as http:
        response = await http.delete(f"/servers/{server_id}")
        response.raise_for_status()
        return response.json()
