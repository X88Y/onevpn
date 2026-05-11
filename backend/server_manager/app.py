import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from server_manager.config import settings
from server_manager.firestore_client import init_firestore
from server_manager.routes.clients import router as clients_router
from server_manager.routes.servers import router as servers_router
from server_manager.routes.subscription import router as subscription_router
from server_manager.workers.health import run_health_loop
from server_manager.workers.install_worker import run_install_loop
from server_manager.workers.traffic_sync import run_traffic_sync_loop
from server_manager.workers.monitoring_sync import run_monitoring_sync_loop

logger = logging.getLogger("server_manager")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level.upper())
    init_firestore()
    tasks = [
        asyncio.create_task(run_install_loop(), name="install_worker"),
        asyncio.create_task(run_traffic_sync_loop(), name="traffic_sync"),
        asyncio.create_task(run_health_loop(), name="health_check"),
        asyncio.create_task(run_monitoring_sync_loop(), name="monitoring_sync"),
    ]
    logger.info("server_manager started workers=%s", [t.get_name() for t in tasks])
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="server_manager", lifespan=_lifespan)
app.include_router(servers_router)
app.include_router(clients_router)
app.include_router(subscription_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}
