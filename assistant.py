import os
import sys
import io
import tempfile
import threading
import anthropic
import requests
import speech_recognition as sr
import pygame

# ── Configuration ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
INWORLD_API_KEY   = os.environ.get("INWORLD_API_KEY", "")
INWORLD_WORKSPACE = "sparklypapaya4999"
INWORLD_VOICE_ID  = "designvoice2b6721f4"
INWORLD_TTS_URL   = (
    f"https://studio.inworld.ai/v1/workspaces/{INWORLD_WORKSPACE}"
    f"/characters/{INWORLD_VOICE_ID}:textToSpeech"
)
MODEL             = "claude-opus-4-8"
SYSTEM_PROMPT     = (
    "You are JARVIS, an advanced AI assistant — highly intelligent, precise, "
    "and slightly formal yet personable. Keep responses concise and clear."
)

# ── Clients / audio init ──────────────────────────────────────────────────────
claude  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
pygame.mixer.init()
recognizer = sr.Recognizer()
conversation_history: list[dict] = []


def speak(text: str) -> None:
    """Convert text to speech via Inworld TTS and play it."""
    try:
        headers = {
            "Authorization": f"Bearer {INWORLD_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"text": text, "voice": {"voiceId": INWORLD_VOICE_ID}}
        resp = requests.post(INWORLD_TTS_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        os.unlink(tmp_path)
    except Exception as e:
        print(f"[TTS error: {e}]")


def ask_claude(user_message: str) -> str:
    """Send a message to Claude and return the response text."""
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
    """Listen for a voice command and return transcribed text, or None on failure."""
    with sr.Microphone() as source:
        print("Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)
            text = recognizer.recognize_google(audio)
            print(f"You said: {text}")
            return text
        except sr.WaitTimeoutError:
            print("No speech detected.")
        except sr.UnknownValueError:
            print("Could not understand audio.")
        except sr.RequestError as e:
            print(f"Speech recognition error: {e}")
    return None


def get_input() -> str | None:
    """Prompt the user: choose mic or text input."""
    print("\n[M] Microphone  [T] Type  [Q] Quit")
    choice = input("Choice: ").strip().upper()
    if choice == "Q":
        return None
    if choice == "M":
        return listen_microphone()
    # default to text
    return input("You: ").strip() or None


def main():
    print("=" * 50)
    print("  JARVIS AI Assistant")
    print("=" * 50)
    print("Say 'exit' or 'quit' to stop.\n")

    if not ANTHROPIC_API_KEY:
        print("WARNING: ANTHROPIC_API_KEY not set.")
    if not INWORLD_API_KEY:
        print("WARNING: INWORLD_API_KEY not set — TTS will be skipped.\n")

    while True:
        user_text = get_input()
        if user_text is None or user_text.lower() in {"exit", "quit"}:
            print("JARVIS: Shutting down. Goodbye.")
            break

        print("JARVIS: thinking...")
        reply = ask_claude(user_text)
        print(f"JARVIS: {reply}\n")

        if INWORLD_API_KEY:
            threading.Thread(target=speak, args=(reply,), daemon=True).start()
            # wait briefly so playback starts before next prompt
            import time; time.sleep(0.3)


if __name__ == "__main__":
    main()
