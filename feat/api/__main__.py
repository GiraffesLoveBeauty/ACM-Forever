from hypercorn.asyncio import serve
from hypercorn.config import Config

from .app import app


def main():
    config = Config()
    config.bind = [
        f"{__import__('os').getenv('ACM_API_HOST', '127.0.0.1')}:"
        f"{__import__('os').getenv('ACM_API_PORT', '8088')}"
    ]
    # The application emits one structured, redacted event per request.
    config.accesslog = None
    config.errorlog = "-"
    import asyncio

    asyncio.run(serve(app, config))


if __name__ == "__main__":
    main()
