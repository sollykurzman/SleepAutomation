#!/usr/bin/python3

import os
import time
import csv
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

DATE = "021225"
DATE_STRING = ["011225", "021225", "031225", "041225"]
ATHLETE_ID = "32447963"
AUTH_FILE = "whoopAuth.json"
EMAIL = os.getenv("WHOOP_EMAIL")
PASSWORD = os.getenv("WHOOP_PASSWORD")

def login_and_save_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating to Whoop Login...")
        page.goto("https://app.whoop.com/login")
        
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except:
            print("Network idle timed out, proceeding anyway...")

        try:
            print("Attempting to autofill credentials...")

            email_input = page.locator('input[type="email"]')
            pass_input = page.locator('input[type="password"]')

            email_input.wait_for(state="visible", timeout=10000)
            
            email_input.click()
            page.wait_for_timeout(500)
            email_input.fill(EMAIL)
            
            pass_input.click()
            page.wait_for_timeout(500)
            pass_input.fill(PASSWORD)
            
            print("Submitting form...")
            page.keyboard.press("Enter")

        except Exception as e:
            print(f"Error during typing: {e}")

        print("Waiting for redirection to Dashboard...")

        try:
            page.wait_for_url("https://app.whoop.com/membership", timeout=30000)
            print("Login detected!")
            
            time.sleep(5) 

            context.storage_state(path=AUTH_FILE)
            print(f"SUCCESS: Session saved to '{AUTH_FILE}'.")
            
        except Exception as e:
            print(f"Login failed or timed out: {e}")
        
        browser.close()

def get_sleep_data(date=DATE):
    data_captured = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=AUTH_FILE)
            page = context.new_page()
        except FileNotFoundError:
            print(f"Error: '{AUTH_FILE}' not found. Run the login script first!")
            return None

        def handle_response(response):
            nonlocal data_captured
            if "sleep-events" in response.url and response.status == 200:
                print(f"Intercepted sleep data from: {response.url}")
                try:
                    data_captured = response.json()
                except:
                    print("Warning: Could not parse JSON from response.")

        page.on("response", handle_response)

        target_url = f"https://app.whoop.com/athlete/{ATHLETE_ID}/sleep/1d/{date}/placeholder"
        
        print(f"Navigating to: {target_url}")
        page.goto(target_url)

        print("Waiting for data stream...")
        for _ in range(20):
            if data_captured:
                break
            page.wait_for_timeout(500)
        
        browser.close()
    
    return data_captured

def save_sleep_data(json_data, filename):
    if not json_data:
        print("No data found. Check the date or your login session.")
        return

    print(f"Processing {len(json_data)} events...")

    stage_map = {
        "SWS": "Deep Sleep",
        "LIGHT": "Core Sleep", 
        "REM": "REM Sleep",
        "WAKE": "Awake",
        "DISTURBANCES": "Disturbance"
    }

    csv_rows = []
    for entry in json_data:
        clean_time = entry['during'].replace("[", "").replace(")", "").replace("'", "")
        start_str, end_str = clean_time.split(",")

        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

        duration_min = (end_dt - start_dt).total_seconds() / 60.0
        
        csv_rows.append({
            "date": start_dt.strftime("%Y-%m-%d"),
            "time": start_dt.strftime("%H:%M:%S"),
            "sleep_state": stage_map.get(entry['type'], entry['type']),
            "end_time": end_dt.strftime("%H:%M:%S"),
            "duration_minutes": round(duration_min, 1),
            "sort_key": start_dt
        })

    csv_rows.sort(key=lambda x: x['sort_key'])

    with open(filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["date", "time", "sleep_state", "end_time", "duration_minutes"])
        
        for row in csv_rows:
            writer.writerow([
                row["date"], 
                row["time"], 
                row["sleep_state"], 
                row["end_time"], 
                row["duration_minutes"]
            ])

    print(f"Saved to {filename}")

def scrape_whoop_data(file):
    date_object = datetime.strptime(file, "%d%m%y")
    date = date_object + timedelta(days=1)
    date = date.strftime("%Y-%m-%d")

    # login_and_save_state()

    if not os.path.exists(f"Data/{file}"):
        os.makedirs(f"Data/{file}")

    sleep_data = get_sleep_data(date=date)
    if sleep_data:
        save_sleep_data(sleep_data, f"Data/{file}/true_sleep_data-{file}.csv")
    else:
        print("No Sleep State data retrieved.")

if __name__ == "__main__":
    for date in DATE_STRING:
        scrape_whoop_data(date)