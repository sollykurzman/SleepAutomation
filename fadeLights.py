import math
import time
import socket
import os
from dotenv import load_dotenv
from requests import Session, RequestException

from Alarm import run_active_alarm

def running_on_pi():
    return socket.gethostname().startswith(("pi",))

load_dotenv()

PI_IP = "192.168.1.39"

BASE_URL = "http://localhost:8123" if running_on_pi() else f"http://{PI_IP}:8123"
HASS_URL = f"{BASE_URL}/api/services"

TOKEN = os.environ.get("HA_AUTH_TOKEN")
if not TOKEN:
    raise RuntimeError("HA_AUTH_TOKEN not set in environment")

ENTITIES = ["light.bed_light", "light.desk_overhead_light", "light.main_bedroom_light"]

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

session = Session()

def set_brightness(level, retries=3, entity_id=ENTITIES):
    """Set brightness with clamping + basic retry logic."""
    level = max(0, min(255, int(level)))  # safe clamp

    payload = {"entity_id": entity_id, "brightness": level}
    for attempt in range(1, retries + 1):
        try:
            r = session.post(
                f"{HASS_URL}/light/turn_on",
                headers=headers,
                json=payload,
                timeout=3
            )
            r.raise_for_status()
            return
        except RequestException as e:
            print(f"Error setting brightness (attempt {attempt}/{retries}): {e}")
            if attempt == retries:
                raise
            time.sleep(0.5)

def fade_lights(duration=1800, steps=255, entities=["light.bed_light", "light.desk_overhead_light", "light.main_bedroom_light"], aware=True, alarm_mode=False, max_brightness=78):
    if aware:
        if os.path.exists("skipnextfadelights"):
            os.remove("skipnextfadelights")
            return
        
    step_time = duration / steps

    start = time.monotonic()

    for i in range(steps + 1):
        x = i / steps
        brightness = max_brightness * (1 - math.cos(x * math.pi)) / 2 
        
        set_brightness(brightness, entity_id=entities)

        next_target = start + (i + 1) * step_time
        sleep_for = next_target - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    if alarm_mode:
        run_active_alarm(aware=aware)

if __name__ == "__main__":
    print("Starting fade...")
    fade_lights()
    print("Fade complete.")
