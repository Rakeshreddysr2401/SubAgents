"""Wake-word listener.

Runs as a standalone process alongside the app. When it hears the configured
wake word it POSTs to /trigger_voice, which pushes a `start_voice` event onto
the browser's /events SSE stream, and the open UI tab auto-starts its mic.

Two engines (set WAKE_WORD_ENGINE in .env):
  - "openwakeword" (default, offline): ONNX detector, no API key, no audio sent
    anywhere. WAKE_WORD is a built-in model name (hey_jarvis, alexa,
    hey_mycroft, hey_rhasspy) or a path to a custom .onnx/.tflite model.
  - "google" (online): Google speech recognition; WAKE_WORD is a phrase to
    substring-match. Sends audio to Google, needs internet.

Install the offline engine's deps:  uv sync --extra wake
Run:                                 uv run python wake_word.py
"""

import logging
import time

import requests

from src.configs.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("wake_word")


def _trigger(url: str) -> None:
    try:
        requests.post(url, timeout=5)
        logger.info(">>> Wake word detected — triggering UI mic")
    except Exception as e:
        logger.warning("Could not reach %s: %s", url, e)


def run_openwakeword(settings) -> None:
    import numpy as np
    import openwakeword
    import sounddevice as sd
    from openwakeword.model import Model

    # Download the shared melspectrogram + embedding models on first run.
    openwakeword.utils.download_models()

    model = Model(wakeword_models=[settings.wake_word])
    key = next(iter(model.models.keys()))
    chunk = 1280  # 80 ms at 16 kHz — openWakeWord's expected frame size

    logger.info(
        "Wake-word listener (openWakeWord) started. Say '%s' (threshold %.2f)...",
        settings.wake_word,
        settings.wake_word_threshold,
    )

    with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=chunk) as stream:
        while True:
            audio, _ = stream.read(chunk)
            score = model.predict(audio.flatten())[key]
            if score >= settings.wake_word_threshold:
                _trigger(settings.trigger_voice_url)
                model.reset()
                time.sleep(settings.wake_word_cooldown_seconds)


def run_google(settings) -> None:
    try:
        import speech_recognition as sr
    except ImportError:
        raise SystemExit("Missing deps for google engine: pip install SpeechRecognition PyAudio")

    r = sr.Recognizer()
    m = sr.Microphone()
    phrase = settings.wake_word.lower()

    logger.info("Wake-word listener (Google) started. Say '%s'...", phrase)
    with m as source:
        r.adjust_for_ambient_noise(source, duration=1)

    while True:
        try:
            with m as source:
                audio = r.listen(source, phrase_time_limit=2)
            text = r.recognize_google(audio).lower()
            logger.info("Heard: %s", text)
            if phrase in text:
                _trigger(settings.trigger_voice_url)
                time.sleep(settings.wake_word_cooldown_seconds)
        except sr.UnknownValueError:
            pass  # background noise
        except Exception as e:
            logger.warning("Error: %s", e)
            time.sleep(1)


def main() -> None:
    settings = get_settings()
    if settings.wake_word_engine == "google":
        run_google(settings)
    else:
        run_openwakeword(settings)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Wake-word listener stopped.")
