#!/usr/bin/python3

import socket
import struct
import time
from datetime import datetime, timedelta, time as dt_time
import threading
import signal
import sys
import statistics
import json
import os

import storeData as store_data
import liveClassify as classifier
import processData as data_processor
from getCalendarData import get_calendar_data
# from Alarm import schedule_alarm

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
PACKETS = 12
BUFFER_SIZE = 4096

def handle_sigterm(signum, frame):
    print("Service stopping?")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def parse_packet(data):
    remainder = len(data) % 2
    if remainder != 0:
        data = data[:-remainder] 
        
    count = len(data) // 2
    if count == 0:
        return []
        
    return struct.unpack(f'<{count}h', data)

def reciever(until=None):

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*1024*1024)
    sock.bind((UDP_IP, UDP_PORT))
    
    print(f"Listening on {UDP_IP}:{UDP_PORT}...")
    first_packet = True

    local_accumulator = []
    BATCH_THRESHOLD = 50 * PACKETS

    try:
        while until is None or datetime.now() < until:
            try:
                data, addr = sock.recvfrom(BUFFER_SIZE)

                if first_packet:
                    print(f"Connected to {addr[0]}:{addr[1]}")
                    first_packet = False
                
                timestamp = time.time()
                adc_values = parse_packet(data)
                
                if not adc_values:
                    continue

                new_entries = [(timestamp, val) for val in adc_values]
                
                local_accumulator.extend(new_entries)

                with store_data.write_lock:
                    store_data.write_queue.extend(new_entries)

                if len(local_accumulator) >= BATCH_THRESHOLD:
                    
                    try:
                        processed_df = data_processor.process_batch(local_accumulator)
 
                        if processed_df is not None and not processed_df.empty:
                            classifier.live_buffer.add_batch(processed_df)
                            
                    except Exception as e:
                        print(f"Error processing batch: {e}")

                    local_accumulator.clear()

            except socket.timeout:
                if not first_packet: print("No data...")
                continue

    except KeyboardInterrupt:
        print("Stopping...")
        sock.close()

def save_event_to_json(event_type: str, timestamp: datetime, JSON_FILE="sleep_events.json"):
    """Store sleep onset or wake-up events in a persistent JSON file."""
    
    # Convert timestamp to string so it can be stored in JSON
    event_record = {
        "type": event_type,
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Load existing events if file exists
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # Append new event
    data.append(event_record)

    # Save back to JSON
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=4)

def monitor_classification_history():
    print("Sleep Tracker Monitor Started...")
    dominant_buffer = classifier.HistoryBuffer(max_length=15)
    asleep = False
    while True:
        if len(classifier.classify_history_buffer.get_data()) < 30:
            time.sleep(1)
            continue
        
        sleep_data = classifier.classify_history_buffer.get_data()
        classifier.classify_history_buffer.clear_data()

        sleep_states = [state for _, state in sleep_data]
        timestamps = [time for time, _ in sleep_data]

        minute_state = statistics.mode(sleep_states)
        dominant_buffer.append(minute_state)

        if len(dominant_buffer.get_data()) >= 15:
            recent_states = dominant_buffer.get_data()
            sleep_count = sum(1 for state in recent_states if state in ["Core Sleep", "Deep Sleep", "REM Sleep"])
            density = sleep_count / len(recent_states)

            current_time = timestamps[-1]

            if density >= 0.75 and not asleep:
                print(f"CONFIRMED SLEEP ONSET: {current_time.strftime('%H:%M:%S')}")
                save_event_to_json("sleep_onset", current_time)
                asleep = True
            elif density < 0.40 and asleep:
                print(f"CONFIRMED WAKE UP: {current_time.strftime('%H:%M:%S')}")
                save_event_to_json("wake_up", current_time)
                asleep = False

if __name__ == "__main__":
    cutoff = dt_time(14, 00, 0, 0)
    today = datetime.now()
    if today.time() < cutoff:
        print("Adjusting date to previous day due to cutoff time")
        today = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    night_id = today.strftime("%d%m%y")
    until = datetime.combine(tomorrow.date(),cutoff)

    print(f"Running data collection and classification until {until} for night: {night_id}")

    events = get_calendar_data(tomorrow.replace(hour=00, minute=00, second=0, microsecond=0))

    events = sorted(events, key=lambda x: x['time'])

    events = [entry for entry in events if 'ignorethis' not in entry['notes']]

    event_time = datetime.combine(datetime.today(), events[0]['time'])

    first_event = event_time - timedelta(hours=1)

    print(first_event.time())

    # schedule_alarm(first_event.time())

    store_data.start_workers(night_id, until)

    classifier.start_workers(night_id, until)

    reciever_thread = threading.Thread(
        target=reciever,
        args=(until,),
        daemon=True
    )
    reciever_thread.start()

    try:
        monitor_classification_history()
    except KeyboardInterrupt:
        print("Stopping Service...")