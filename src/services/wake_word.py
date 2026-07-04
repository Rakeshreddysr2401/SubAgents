"""Reusable wake-word detection loop.

`run_listener` runs a blocking audio loop until `stop_event` is set, invoking
`on_detect()` each time the wake word fires. It is shared by two callers:

  - the standalone CLI (`wake_word.py`), whose on_detect POSTs /trigger_voice
  - the in-process background thread (src/app.py), whose on_detect fans out to
    /events subscribers directly

Engines (WAKE_WORD_ENGINE): "openwakeword" (offline ONNX) or "google" (online).
"""

import logging
import threading
from typing import Callable

logger = logging.getLogger("wake_word")


def run_openwakeword(settings, on_detect: Callable[[], None], stop_event: threading.Event) -> None:
    import numpy as np
    import openwakeword
    import sounddevice as sd
    from openwakeword.model import Model

    openwakeword.utils.download_models()  # shared base models, once
    model = Model(wakeword_models=[settings.wake_word])
    key = next(iter(model.models.keys()))
    chunk = 1280  # 80 ms at 16 kHz — openWakeWord's expected frame size

    logger.info(
        "Wake-word listener (openWakeWord) started. Say '%s' (threshold %.2f)...",
        settings.wake_word,
        settings.wake_word_threshold,
    )
    with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=chunk) as stream:
        while not stop_event.is_set():
            audio, _ = stream.read(chunk)
            score = model.predict(audio.flatten())[key]
            if score >= settings.wake_word_threshold:
                on_detect()
                model.reset()
                stop_event.wait(settings.wake_word_cooldown_seconds)


def run_google(settings, on_detect: Callable[[], None], stop_event: threading.Event) -> None:
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

    while not stop_event.is_set():
        try:
            with m as source:
                audio = r.listen(source, phrase_time_limit=2)
            text = r.recognize_google(audio).lower()
            logger.info("Heard: %s", text)
            if phrase in text:
                on_detect()
                stop_event.wait(settings.wake_word_cooldown_seconds)
        except sr.UnknownValueError:
            pass  # background noise
        except Exception as e:
            logger.warning("Error: %s", e)
            stop_event.wait(1)


def run_listener(settings, on_detect: Callable[[], None], stop_event: threading.Event) -> None:
    if settings.wake_word_engine == "google":
        run_google(settings, on_detect, stop_event)
    else:
        run_openwakeword(settings, on_detect, stop_event)
