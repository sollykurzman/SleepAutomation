import math
import time
from requests import get, post
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.environ.get("HA_AUTH_TOKEN")
HASS_URL = "http://localhost:8123/api/services"
ENTITY_ID = "light.bed_light"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

response = get(HASS_URL, headers=headers)

def set_brightness(level):
    post(
        f"{HASS_URL}/light/turn_on",
        headers=headers,
        json={"entity_id": ENTITY_ID, "brightness": int(level)},
    )

duration = 5  # seconds
steps = 50
for i in range(steps + 1):
    x = i / steps
    brightness = 255 * (1 - math.cos(x * math.pi)) / 2  # cosine ease-in-out
    set_brightness(brightness)
    time.sleep(duration / steps)