import os
from requests import get, post
import json
from dotenv import load_dotenv

load_dotenv()

IP = os.environ.get("HA_IP")

TOKEN = os.environ.get("HA_AUTH_TOKEN")

# print(IP)
# print(TOKEN)

url = "http://localhost:8123/api/services"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "content-type": "application/json",
}

response = get(url, headers=headers)
# print(response.text)

url = "http://localhost:8123/api/services/light/turn_on"
headers = {"Authorization": f"Bearer {TOKEN}"}
data = {
    "entity_id": "light.bed_light",
    "brightness": 50,
    "transition": 600
    }

response = post(url, headers=headers, json=data)
print(response.text)