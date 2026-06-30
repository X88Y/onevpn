import uvicorn
from remnawave_webhook_server.config import webhook_host, webhook_port

if __name__ == "__main__":
    host = webhook_host()
    port = webhook_port()
    print(f"Starting Remnawave Webhook Server on {host}:{port}")
    uvicorn.run("remnawave_webhook_server.app:app", host=host, port=port, reload=True)
