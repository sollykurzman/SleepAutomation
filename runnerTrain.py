#!/usr/bin/python3

from datetime import datetime, timedelta, time as dt_time
import signal
import sys
import os
import csv

import scrapeWhoopData
import formatData
import trainModels

def handle_sigterm(signum, frame):
    print("Service stopping?")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def has_untrained_folders():
    data_path = "Data"
    folder_names = [
        name for name in os.listdir(data_path)
        if os.path.isdir(os.path.join(data_path, name))
    ]
    
    trained_csv_path = os.path.join("ML", "trained.csv")
    trained_folders = set()

    with open(trained_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trained_folders.add(row["date"])
            
    return any(folder not in trained_folders for folder in folder_names)

def add_trained_date(date_value):
    csv_path = os.path.join("ML", "trained.csv")
    
    existing = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing.add(row["date"])

    if date_value in existing:
        return False
    
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([date_value])

    return True



if __name__ == "__main__":
    cutoff = dt_time(14, 00, 0, 0)
    today = datetime.now()
    if today.time() < cutoff:
        print("Adjusting date to previous day due to cutoff time")
        today = today - timedelta(days=1)
    yesterday = today - timedelta(days=1)
    night_id = yesterday.strftime("%d%m%y")
    print(f"Processing night ID: {night_id}")

    if has_untrained_folders():

        print(f"Scraping Whoop data for night: {night_id}...")
        scrapeWhoopData.scrape_whoop_data(night_id)
        print("Formatting data...")
        formatData.run(reformat=False)
        print("Training models...")
        trainModels.train_all_models()
        print("Scraping and Training Done.")
        add_trained_date(night_id)
    
    else:
        print("No new data to train model.")
