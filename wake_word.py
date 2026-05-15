import requests
import time
import os

# To run this, you need: pip install SpeechRecognition PyAudio
try:
    import speech_recognition as sr
except ImportError:
    print("Missing dependencies! Run: pip install SpeechRecognition PyAudio")
    exit(1)

# CONFIGURATION
WAKE_WORD = "assistant"  # Change this to whatever you like
TRIGGER_URL = "http://localhost:2024/trigger_voice"

def listen_for_wake_word():
    r = sr.Recognizer()
    m = sr.Microphone()

    print(f"Wake-word listener started. Say '{WAKE_WORD}' to trigger the AI...")

    with m as source:
        r.adjust_for_ambient_noise(source, duration=1)

    while True:
        try:
            with m as source:
                # phrase_time_limit keeps the listening window short
                audio = r.listen(source, phrase_time_limit=2)
            
            # Use Google's free local-ish STT for the wake word
            text = r.recognize_google(audio).lower()
            print(f"Heard: {text}")

            if WAKE_WORD in text:
                print(">>> Wake word detected! Triggering UI...")
                requests.post(TRIGGER_URL)
                # Brief sleep to avoid double-triggering
                time.sleep(2)

        except sr.UnknownValueError:
            # Just background noise
            pass
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    listen_for_wake_word()
