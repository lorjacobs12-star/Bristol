import base64
import io
import os
import sys
import threading
import numpy as np
import sounddevice as sd
import anthropic
import requests
import speech_recognition as sr
import pygame
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
INWORLD_API_KEY   = os.getenv("INWORLD_API_KEY")
INWORLD_VOICE_ID  = os.getenv("INWORLD_VOICE_ID")

if not all([ANTHROPIC_API_KEY, INWORLD_API_KEY, INWORLD_VOICE_ID]):
    print("ERROR: Missing API keys. Check your .env file.")
    sys.exit(1)

MODEL = "claude-opus-4-8"
SYSTEM_PROMPT = (
    "You are JARVIS, an advanced AI assistant. You are intelligent, precise, and efficient. "
    "Respond concisely and naturally as JARVIS would — helpful, professional, and occasionally witty. "
    "Keep responses short unless detail is specifically requested."
)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
pygame.mixer.init()
recognizer = sr.Recognizer()
conversation_history: list[dict] = []


def speak(text: str) -> None:
    try:
        response = requests.post(
            "https://api.inworld.ai/tts/v1/voice",
            headers={
                "Authorization": f"Basic {INWORLD_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "voiceId": INWORLD_VOICE_ID,
                "modelId": "inworld-tts-1.5-max",
                "text": text,
                "audioConfig": {"audioEncoding": "WAV"},
            },
            timeout=30,
        )
        response.raise_for_status()
        audio_bytes = base64.b64decode(response.json()["audioContent"])
        sound = pygame.mixer.Sound(io.BytesIO(audio_bytes))
        channel = sound.play()
        while channel.get_busy():
            pygame.time.wait(50)
    except Exception as e:
        print(f"[TTS error: {e}]")


def ask_claude(user_message: str) -> str:
    conversation_history.append({"role": "user", "content": user_message})
    response = claude.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=conversation_history,
    )
    reply = next(
        (b.text for b in response.content if b.type == "text"),
        "I'm sorry, I didn't generate a response."
    )
    conversation_history.append({"role": "assistant", "content": reply})
    return reply


def listen_microphone() -> str | None:
    sample_rate = 16000
    duration = 8  # seconds max

    print("Listening... (speak now)")
    recording = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()

    audio_data = recording.flatten().tobytes()
    audio = sr.AudioData(audio_data, sample_rate, 2)
    try:
        text = recognizer.recognize_google(audio)
        print(f"You said: {text}")
        return text
    except sr.UnknownValueError:
        print("Could not understand audio.")
    except sr.RequestError as e:
        print(f"Speech recognition error: {e}")
    return None


def get_input() -> str | None:
    print("\n[M] Microphone  [T] Type  [Q] Quit")
    choice = input("Choice: ").strip().upper()
    if choice == "Q":
        return None
    if choice == "M":
        return listen_microphone()
    return input("You: ").strip() or None


def main() -> None:
    print("=" * 50)
    print("  JARVIS AI Assistant")
    print("=" * 50)
    print("Say 'exit' or 'quit' to stop.\n")

    while True:
        user_text = get_input()
        if user_text is None or user_text.lower() in {"exit", "quit"}:
            print("JARVIS: Shutting down. Goodbye.")
            break

        print("JARVIS: thinking...")
        reply = ask_claude(user_text)
        print(f"JARVIS: {reply}\n")
        threading.Thread(target=speak, args=(reply,), daemon=True).start()


if __name__ == "__main__":
    main()
