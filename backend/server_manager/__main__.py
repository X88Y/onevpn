import uvicorn

from server_manager.config import settings


def main() -> None:
    uvicorn.run(
        "server_manager.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
