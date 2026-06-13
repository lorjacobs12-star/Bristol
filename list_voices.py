import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("INWORLD_API_KEY")
if not API_KEY:
    print("ERROR: INWORLD_API_KEY not set in .env")
    raise SystemExit(1)

resp = requests.get(
    "https://api.inworld.ai/tts/v1/voices",
    headers={"Authorization": f"Basic {API_KEY}"},
    timeout=15,
)
resp.raise_for_status()
voices = resp.json().get("voices", [])

print(f"Found {len(voices)} voices:\n")
for v in voices:
    print(f"  ID: {v.get('voiceId')}  Name: {v.get('name')}  Gender: {v.get('gender')}")
