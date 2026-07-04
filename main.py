"""Uvicorn entry point.

    uv run uvicorn main:app --host 0.0.0.0 --port 2024
"""

from src.app import create_app

app = create_app()
