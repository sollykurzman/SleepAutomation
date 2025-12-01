#!/usr/bin/python3

import socket
import struct
import time
from datetime import datetime, timedelta, time as dt_time, date as dt_date
import threading
import signal
import sys
import statistics
import json
import os
from dataclasses import dataclass
import subprocess
from collections import deque
import pandas as pd
from scipy.signal import find_peaks

import storeData as store_data
import liveClassify as classifier
import processData as data_processor
from getCalendarData import get_calendar_data
from fadeLights import fade_lights

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
PACKETS = 12
BUFFER_SIZE = 4096
HOURS_GOAL = 8.0

def handle_sigterm(signum, frame):
    print("Service stopping?")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

dominant_history = deque(maxlen=1440)

@dataclass(frozen=True)
class NightContext:
    cutoff: dt_time
    today: datetime
    tomorrow: datetime
    night_id: str
    until: datetime

def build_night_context(cutoff, today):
    if today.time() < cutoff:
        today = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    night_id = today.strftime("%d%m%y")
    until = datetime.combine(tomorrow.date(), cutoff)

    return NightContext(
        cutoff=cutoff,
        today=today,
        tomorrow=tomorrow,
        night_id=night_id,
        until=until
    )

class NightState:
    def __init__(self, first_event_time):
        self._lock = threading.Lock()
        self._first_event_time = first_event_time
        self._alarm_scheduled = None

    def get_first_event_time(self):
        with self._lock:
            return self._first_event_time

    def set_first_event_time(self, value):
        with self._lock:
            self._first_event_time = value

    def get_alarm_scheduled(self):
        with self._lock:
            return self._alarm_scheduled

    def set_alarm_scheduled(self, value):
        with self._lock:
            self._alarm_scheduled = value

def parse_packet(data):
    remainder = len(data) % 2
    if remainder != 0:
        data = data[:-remainder] 
        
    count = len(data) // 2
    if count == 0:
        return []
        
    return struct.unpack(f'<{count}h', data)

def reciever(until=None, night_id=None):

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
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
                    if night_id:
                        save_event_to_json(
                            "receiver_first_packet",
                            datetime.now(),
                            file_path=f"Data/{night_id}/sleep_events-{night_id}.json"
                        )
                
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
                        if night_id:
                            log_error_to_json(
                                f"Error processing batch: {e}",
                                file_path=f"Data/{night_id}/sleep_events-{night_id}.json"
                            )

                    local_accumulator.clear()

            except socket.timeout:
                if not first_packet: print("No data...")
                continue

    except KeyboardInterrupt:
        print("Stopping...")
        sock.close()

from datetime import datetime, date as dt_date, timedelta

def schedule_alarm(alarm_time, date=None, night_context=None, night_state=None):
    if isinstance(alarm_time, str):
        alarm_time = datetime.strptime(alarm_time, "%H:%M:%S").time()

    now = datetime.now()

    if date is not None:
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d").date()

        alarm_dt = datetime.combine(date, alarm_time)
        date_str = date.strftime('%Y-%m-%d')
    else:
        today = now.date()
        if night_context is not None:
            today = night_context.tomorrow.date()
        alarm_dt = datetime.combine(today, alarm_time)
        if alarm_dt <= now:
            alarm_dt += timedelta(days=1)

        date_str = "*-*-*"

    delta = alarm_dt - datetime.now()
    mins_until = int(delta.total_seconds() / 60)

    if 0 <= mins_until <= 30:
        print("Alarm is within 30 minutes, doing alternate behaviour")
        with open("skipnextalarm", "w") as f:
            pass
        with open("skipnextfadelights", "w") as f:
            pass
        seconds_left = mins_until * 60
        steps = max(1, min(seconds_left // 2, 255))
        threading.Thread(
            target=fade_lights,
            kwargs={
                "duration": seconds_left,
                "steps": steps,
                "aware": False,
                "alarm_mode": True
            }
        ).start()
        return

    fade_dt = alarm_dt - timedelta(minutes=30)

    if date is not None:
        fade_date_str = fade_dt.date().strftime('%Y-%m-%d')
    else:
        # recurring timer: only care about the time; date is wildcard
        fade_date_str = "*-*-*"

    fade_time = fade_dt.time()

    # ---- Build unit contents ----
    new_contents = f"""[Unit]
Description=Alarm timer

[Timer]
OnCalendar={date_str} {alarm_time.strftime('%H:%M:%S')}

[Install]
WantedBy=timers.target"""

    new_fade_lights_contents = f"""[Unit]
Description=Fade Lights timer

[Timer]
OnCalendar={fade_date_str} {fade_time.strftime('%H:%M:%S')}

[Install]
WantedBy=timers.target"""

    # ---- Apply timers ----
    subprocess.run(["sudo", "/usr/local/bin/update_alarm_timer", new_contents])
    subprocess.run(["sudo", "/usr/local/bin/update_fade_lights_timer", new_fade_lights_contents])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "restart", "alarm.timer"])
    subprocess.run(["sudo", "systemctl", "restart", "fade_lights.timer"])

    if night_state:
        night_state.set_alarm_scheduled(alarm_dt)

    if night_context:
        update_event_in_json(
            "alarm_set",
            alarm_dt,
            file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json",
        )


def return_first_event_time(search_date):
    events = get_calendar_data(search_date)

    events = sorted(events, key=lambda x: x['time'])

    events = [
        entry for entry in events
        if 'notes' in entry and 'ignorethis' not in entry['notes']
    ]

    if not events:
        return datetime.strptime("10:00:00", "%H:%M:%S").time()

    event_time = datetime.combine(datetime.today(), events[0]['time'])

    first_event = event_time - timedelta(hours=1)

    return first_event.time()

def calculate_sleep_time(json_path):
    with open(json_path, 'r') as f:
        events = json.load(f)

    for e in events:
        e["timestamp"] = datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S")
    events.sort(key=lambda x: x["timestamp"])

    sleep_periods = []
    last_sleep_onset = None

    for event in events:
        if event["type"] == "sleep_onset":
            last_sleep_onset = event["timestamp"]

        elif event["type"] == "wake_up" and last_sleep_onset:
            sleep_periods.append((last_sleep_onset, event["timestamp"]))
            last_sleep_onset = None

        elif event["type"] == "alarm_set":
            if last_sleep_onset:
                sleep_periods.append((last_sleep_onset, event["timestamp"]))
                last_sleep_onset = None

    total_sleep_seconds = sum((end - start).total_seconds() for start, end in sleep_periods)
    total_sleep_hours = total_sleep_seconds / 3600

    return total_sleep_hours

def calculate_sleep_debt(night_context, past_days=7):
    search_dates = list([(night_context.today - timedelta(days=i)).strftime("%d%m%y") for i in range(1, past_days + 1)])
    print(search_dates)
    search_paths = list([f"Data/{night_id}/sleep_events-{night_id}.json" for night_id in search_dates])
    print(search_paths)
    sleep_hours = []
    for search_path in search_paths:
        if os.path.exists(search_path):
            hours = calculate_sleep_time(search_path)
            sleep_hours.append(hours)

    return sum(HOURS_GOAL - x for x in sleep_hours)

def sleep_onset_action(night_context, night_state, timestamp):
    try:
        new_first_event_time = return_first_event_time(night_context.tomorrow.replace(hour=00, minute=00, second=0, microsecond=0))

        sleep_debt = calculate_sleep_debt(night_context)
        search_path = f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json"
        if os.path.exists(search_path):
            slept_today = calculate_sleep_time(search_path)
        else:
            slept_today = 0.0
        hours = HOURS_GOAL - slept_today + sleep_debt
        wake_today = timestamp + timedelta(hours=hours)

        save_event_to_json(
            "ideal_wake_from_sleep_debt",
            wake_today,
            file_path=search_path,
        )

        new_first_event_time = min(new_first_event_time, wake_today.time())

        if new_first_event_time != night_state.get_first_event_time():
            print(f"Updating first event time to {new_first_event_time.strftime('%H:%M:%S')}")
            night_state.set_first_event_time(new_first_event_time)
            schedule_alarm(new_first_event_time.strftime("%H:%M:%S"), night_context=night_context, night_state=night_state)
    except Exception as e:
        log_error_to_json(
            f"sleep_onset_action crashed: {e}",
            file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json"
        )

def save_event_to_json(event_type, timestamp, file_path="sleep_events.json"):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    event_record = {
        "type": event_type,
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []
        
    data.append(event_record)
    
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

def update_event_in_json(event_type, timestamp, file_path="sleep_events.json"):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    event_record = {
        "type": event_type,
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Load existing data
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # Look for an existing event with same type
    updated = False
    for i, event in enumerate(data):
        if event.get("type") == event_type:
            data[i] = event_record  # overwrite existing record
            updated = True
            break

    # If no existing event was updated, append a new one
    if not updated:
        data.append(event_record)

    # Save back to file
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

def log_error_to_json(message, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    event_record = {
        "type": "error",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": str(message)
    }

    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = []
    else:
        data = []

    data.append(event_record)

    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

def core_sleep_action(night_context, night_state):
    try:
        history = list(dominant_history)
        if not history:
            save_event_to_json(
                "no_history_for_core_sleep",
                datetime.now(),
                file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json",
            )
            return

        df = pd.DataFrame(history)

        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

        # Drop rows where timestamp conversion failed
        df = df.dropna(subset=['timestamp'])

        # Create a core indicator
        df['is_core'] = df['state'].str.lower().str.contains('core').astype(int)

        df = df.set_index('timestamp').sort_index()
        sample_check = df['is_core'].resample('1min').max().fillna(0)

        WINDOW_SIZE = '20min' 
        smooth_signal = sample_check.rolling(window=WINDOW_SIZE, center=True).mean()

        peaks_indices, _ = find_peaks(
            smooth_signal.values, 
            distance=70,       # Minimum distance between peaks (in minutes)
            height=0.4,        # Intensity threshold (0.4 means 40% of the window was 'core')
            prominence=0.1     # Peak must stand out relative to neighbors
        )

        peak_times = smooth_signal.index[peaks_indices]
        intervals = pd.Series(peak_times).diff().dropna()

        if len(peak_times) < 2 or intervals.empty:
            print("No core sleep peaks detected for core sleep action.")
            save_event_to_json(
                "no_core_peaks_detected",
                datetime.now(),
                file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json",
            )
            return
    
        intervals_mins = intervals.dt.total_seconds() / 60

        valid_cycles = intervals_mins[(intervals_mins >= 70) & (intervals_mins <= 120)]

        if valid_cycles.empty or pd.isna(avg_cycle):
            print("No valid core sleep cycles found; skipping core sleep adjustment.")
            save_event_to_json(
                "no_valid_core_cycles",
                datetime.now(),
                file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json",
            )
            return

        avg_cycle = valid_cycles.median()

        last_peak = peak_times[-1]

        next_prediction = last_peak + pd.Timedelta(minutes=avg_cycle)

        alarm_dt = night_state.get_alarm_scheduled()
        if alarm_dt is not None and next_prediction <= alarm_dt <= next_prediction + timedelta(minutes=30):
        # if next_prediction <= night_state.get_alarm_scheduled() <= next_prediction + timedelta(minutes=30):
            print(f"Adjusting alarm to core sleep peak at {next_prediction.strftime('%H:%M:%S')}")
            save_event_to_json(
                "core_sleep_alarm_set: " + next_prediction.strftime('%H:%M:%S'),
                datetime.now(),
                file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json",
            )
            schedule_alarm(
                next_prediction.time().strftime("%H:%M:%S"),
                date=night_context.tomorrow.date(),
                night_context=night_context,
                night_state=night_state
            )
    except Exception as e:
        log_error_to_json(
            f"core_sleep_action failed: {e}",
            file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json"
        )
        return

def monitor_classification_history(night_context, night_state):
    print("Sleep Tracker Monitor Started...")
    dominant_buffer = classifier.HistoryBuffer(max_length=15)
    asleep = False
    actionedCore = False
    while True:
        try:
            if len(classifier.classify_history_buffer.get_data()) < 30:
                time.sleep(1)
                continue
            
            sleep_data = classifier.classify_history_buffer.get_data()
            classifier.classify_history_buffer.clear_data()

            sleep_states = [state for _, state in sleep_data]
            timestamps = [time for time, _ in sleep_data]

            minute_state = statistics.mode(sleep_states)
            dominant_buffer.add_data(minute_state)
            dominant_history.append({
                "timestamp": datetime.now(),
                "state": minute_state
            })

            if len(dominant_buffer.get_data()) >= 15:
                recent_states = dominant_buffer.get_data()
                sleep_count = sum(1 for state in recent_states if state in ["Core Sleep", "Deep Sleep", "REM Sleep"])
                density = sleep_count / len(recent_states)

                current_time = timestamps[-1]

                if density >= 0.75 and not asleep:
                    print(f"CONFIRMED SLEEP ONSET: {current_time.strftime('%H:%M:%S')}")
                    save_event_to_json("sleep_onset", current_time, file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json")
                    threading.Thread(
                        target=sleep_onset_action,
                        args=(night_context, night_state, current_time),
                        daemon=True
                    ).start()
                    asleep = True
                elif density < 0.40 and asleep:
                    print(f"CONFIRMED WAKE UP: {current_time.strftime('%H:%M:%S')}")
                    save_event_to_json("wake_up", current_time, file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json")
                    asleep = False
                
                alarm_dt = night_state.get_alarm_scheduled()
                if alarm_dt is not None and current_time <= alarm_dt <= current_time + timedelta(minutes=60) and not actionedCore:
                # if current_time <= night_state.get_alarm_scheduled() <= current_time + timedelta(minutes=60) and not actionedCore:
                    threading.Thread(
                        target=core_sleep_action,
                        args=(night_context, night_state),
                        daemon=True
                    ).start()
                    actionedCore = True
        except Exception as e:
            log_error_to_json(
                f"monitor_classification_history error: {e}",
                file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json"
            )
            time.sleep(1)
            


if __name__ == "__main__":
    cutoff = dt_time(14, 00, 0, 0)
    today = datetime.now()

    night_context = build_night_context(cutoff, today)

    save_event_to_json(
        "service_started",
        datetime.now(),
        file_path=f"Data/{night_context.night_id}/sleep_events-{night_context.night_id}.json"
    )

    print(f"Running data collection and classification until {night_context.until} for night: {night_context.night_id}")

    first_event_time = return_first_event_time(night_context.tomorrow.replace(hour=00, minute=00, second=0, microsecond=0))
    night_state = NightState(first_event_time)

    print(first_event_time)

    sleep_onset_action(night_context, night_state, datetime.now())

    schedule_alarm(first_event_time.strftime("%H:%M:%S"), night_context=night_context, night_state=night_state)

    store_data.start_workers(night_context.night_id, night_context.until)

    classifier.start_workers(night_context.night_id, night_context.until)

    reciever_thread = threading.Thread(
        target=reciever,
        args=(night_context.until,night_context.night_id),
        daemon=True
    )
    reciever_thread.start()

    try:
        monitor_classification_history(night_context, night_state)
    except KeyboardInterrupt:
        print("Stopping Service...")