"""The ASGI entry point. Run: uv run uvicorn wayfinder.api.main:app"""

from wayfinder.api.app import create_app

app = create_app()
