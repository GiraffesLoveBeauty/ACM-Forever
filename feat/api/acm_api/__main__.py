import asyncio
import os

from hypercorn.asyncio import serve
from hypercorn.config import Config

from .app import app


def main():
    config = Config()
    host = os.getenv("ACM_API_HOST", "127.0.0.1")
    port = os.getenv("ACM_API_PORT", "8090")
    config.bind = [f"{host}:{port}"]
    config.accesslog = "-"
    config.errorlog = "-"
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    main()
