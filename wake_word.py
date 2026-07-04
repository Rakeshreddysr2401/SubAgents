"""Standalone wake-word listener (CLI).

Runs the detector as a separate process and POSTs /trigger_voice when the wake
word fires — useful when the mic is on a different machine than the server.

For the single-machine case, prefer WAKE_WORD_ENABLED=true, which runs the same
detector inside the server process (no separate command needed).

Install offline engine deps:  uv sync --extra wake
Run:                          uv run python wake_word.py
"""

import logging
import threading

import requests

from src.configs.settings import get_settings
from src.services.wake_word import run_listener

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("wake_word")


def main() -> None:
    settings = get_settings()

    def on_detect() -> None:
        try:
            requests.post(settings.trigger_voice_url, timeout=5)
            logger.info(">>> Wake word detected — triggering UI mic")
        except Exception as e:
            logger.warning("Could not reach %s: %s", settings.trigger_voice_url, e)

    stop_event = threading.Event()
    try:
        run_listener(settings, on_detect, stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        logger.info("Wake-word listener stopped.")


if __name__ == "__main__":
    main()
