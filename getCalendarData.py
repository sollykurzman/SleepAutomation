import os
import requests
from ics import Calendar
from icalendar import Calendar as icloudCal
from dotenv import load_dotenv
import datetime
import caldav

load_dotenv()

UNI_CALENDAR_URL = os.environ.get("UNI_CALENDAR_URL")
PERSONAL_CALENDAR_URL = os.environ.get("PERSONAL_CALENDAR_URL")
APPLE_ID = os.environ.get("APPLE_ID")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

def get_calendar_data(date):
    tomorrows_events = []

    try:
        with caldav.DAVClient(url=PERSONAL_CALENDAR_URL, username=APPLE_ID, password=APP_PASSWORD) as client:
            my_principal = client.principal()

            calendars = my_principal.calendars()
            next_day = date + datetime.timedelta(days=1)
            for calendar in calendars:
                icloud_events = calendar.date_search(start=date, end=next_day, expand=True)
                for icloud_event in icloud_events:
                    event = icloudCal.from_ical(icloud_event.data).walk('vevent')[0]
                    tomorrows_events.append({
                        "title":event.get('summary', 'No Title'),
                        "time":event.get('dtstart').dt.time(),
                        "location":event.get('location', 'No Location'),
                        "notes": event.get('description', 'No Notes')
                    })
        
    except Exception as e:
        print(f"Error connecting to iCloud: {e}")
        exit(1)

    try:
        cal_data = requests.get(UNI_CALENDAR_URL).text
        c = Calendar(cal_data)
    except Exception as e:
        print(f"Error downloading or parsing calendar: {e}")
        exit()
        
    all_events = list(c.events)

    if not all_events:
        print("No events found in the calendar.")

    for event in all_events:
        if event.begin.date() == date:
            tomorrows_events.append({
                "title":(event.name or "No Title"),
                "time":event.begin.time(),
                "location":(event.location or 'No Location'),
                "notes": (event.description or 'No Notes')
            })

    return tomorrows_events

if __name__ == "__main__":
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    events = get_calendar_data(tomorrow)
    print(f"Earliest Scheduled Event Tomorrow is at: {sorted(events, key=lambda x: x['time'])[0]['time']}")