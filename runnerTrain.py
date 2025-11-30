#!/usr/bin/python3

from datetime import datetime, timedelta, time as dt_time
import signal
import sys

import scrapeWhoopData
import formatData
import trainModels

def handle_sigterm(signum, frame):
    print("Service stopping?")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

if __name__ == "__main__":
    cutoff = dt_time(14, 00, 0, 0)
    today = datetime.now()
    if today.time() < cutoff:
        print("Adjusting date to previous day due to cutoff time")
        today = today - timedelta(days=1)
    yesterday = today - timedelta(days=1)
    night_id = yesterday.strftime("%d%m%y")
    print(f"Processing night ID: {night_id}")

    print(f"Scraping Whoop data for night: {night_id}...")
    scrapeWhoopData.scrape_whoop_data(night_id)
    print("Formatting data...")
    formatData.run(reformat=False)
    print("Training models...")
    trainModels.train_all_models()
    print("Scraping and Training Done.")
