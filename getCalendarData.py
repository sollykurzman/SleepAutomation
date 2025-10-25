import os
import requests
from ics import Calendar
from icalendar import Calendar as icloudCal
from dotenv import load_dotenv
import datetime
import caldav

# export ICLOUD_EMAIL='your-apple-id@email.com', unset to remove
# export ICLOUD_PASSWORD='xxxx-xxxx-xxxx-xxxx', unset to remove
load_dotenv()

UNI_CALENDAR_URL = os.environ.get("UNI_CALENDAR_URL")
PERSONAL_CALENDAR_URL = os.environ.get("PERSONAL_CALENDAR_URL")
APPLE_ID = os.environ.get("APPLE_ID")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

today = datetime.date.today()
tomorrow = today + datetime.timedelta(days=1)
overmorrow = today + datetime.timedelta(days=2)

tomorrows_events = []

try:
    # Connect to the service
    with caldav.DAVClient(url=PERSONAL_CALENDAR_URL, username=APPLE_ID, password=APP_PASSWORD) as client:
        my_principal = client.principal()

        calendars = my_principal.calendars()

        for calendar in calendars:
            icloud_events = calendar.search(start=tomorrow, end=overmorrow, expand=True)
            for icloud_event in icloud_events:
                event = icloudCal.from_ical(icloud_event.data).walk('vevent')[0]
                tomorrows_events.append({
                    "title":event.get('summary', 'No Title'),
                    "time":event.get('dtstart').dt.time(),
                    "location":event.get('location', 'No Location')
                })
    
except Exception as e:
    print(f"Error connecting to iCloud: {e}")
    # This often happens if the password is wrong
    exit(1)

try:
    # Get the calendar data
    cal_data = requests.get(UNI_CALENDAR_URL).text
    c = Calendar(cal_data)
except Exception as e:
    print(f"Error downloading or parsing calendar: {e}")
    exit()
    
all_events = list(c.events)

if not all_events:
    print("No events found in the calendar.")

for event in all_events:
    # We only care about events that are today or in the future
    if event.begin.date() == tomorrow:
        tomorrows_events.append({
            "title":(event.name or "No Title"),
            "time":event.begin.time(),
            "location":(event.location or 'No Location')
        })

print(sorted(tomorrows_events, key=lambda x: x['time']))
print(f"Earliest Scheduled Event Tomorrow is at: {sorted(tomorrows_events, key=lambda x: x['time'])[0]['time']}")