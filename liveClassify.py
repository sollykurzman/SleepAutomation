#!/usr/bin/python3

import socket
import struct
import time
import os
from datetime import datetime
import threading
from collections import deque
import pandas as pd
import joblib
# import queue

import processData as data_processor
from formatData import process_window, add_history_features

UDP_IP = "0.0.0.0"
UDP_PORT_CAPACITANCE = 5005
BUFFER_SIZE = 4096
PACKETS = 12
ML_INTERVAL = 2.0
PATH = "ML/"

in_bed_model = joblib.load(PATH + 'in_bed_model.joblib')
in_bed_model.verbose = 0
in_bed_encoder = joblib.load(PATH + 'in_bed_encoder.joblib')    

asleep_model = joblib.load(PATH + 'asleep_model.joblib')
asleep_model.verbose = 0
asleep_encoder = joblib.load(PATH + 'asleep_encoder.joblib')

state_model = joblib.load(PATH + 'state_model.joblib')
state_model.verbose = 0
state_encoder = joblib.load(PATH + 'state_encoder.joblib')

# result_queue = queue.Queue()

class RollingBuffer:
    def __init__(self, window_seconds, sample_rate):
        self.max_len = int(window_seconds * sample_rate)
        self.buffer = deque(maxlen=self.max_len)
        self.lock = threading.Lock()
        
    def add_batch(self, df):
        if df is None or df.empty:
            return
        
        new_data = list(zip(df['datetime'], df['voltage']))
        
        with self.lock:
            self.buffer.extend(new_data)
            
    def get_snapshot(self):
        with self.lock:
            data_snapshot = list(self.buffer)

        if len(data_snapshot) < self.max_len:
            return None, None
        
        times, voltages = zip(*data_snapshot)
        return list(times), list(voltages)
    
live_buffer = RollingBuffer(window_seconds=30, sample_rate=100)

class HistoryBuffer:
    def __init__(self, max_length):
        self.buffer = deque(maxlen=max_length)
        self.lock = threading.Lock()
        
    def add_data(self, data):
        with self.lock:
            self.buffer.append(data)
            
    def get_data(self):
        with self.lock:
            return list(self.buffer)
        
    def clear_data(self):
        with self.lock:
            self.buffer.clear()
        
history_buffer = HistoryBuffer(max_length=12)
classify_history_buffer = HistoryBuffer(max_length=30)

def predict_with_model(model, encoder, full_data_row):
    required_features = model.feature_names_in_
    
    X_specific = full_data_row[required_features]
    
    prediction_raw = model.predict(X_specific)
    label = encoder.inverse_transform(prediction_raw)[0]
    
    return label

def classify_snippet(snippet):

    X_input = snippet.drop(columns=['timestamp'])

    ib_label = predict_with_model(in_bed_model, in_bed_encoder, X_input)

    if ib_label == 'inBed':
        slp_label = predict_with_model(asleep_model, asleep_encoder, X_input)
        if slp_label == 'Asleep':
            state_label = predict_with_model(state_model, state_encoder, X_input)
            return state_label#f"{ib_label}, {slp_label}, {state_label}"
        else:
            return slp_label#f"{ib_label}, {slp_label}"
    else:
        return ib_label#f"{ib_label}"

def parse_packet(data):
    remainder = len(data) % 2
    if remainder != 0:
        data = data[:-remainder] 
        
    count = len(data) // 2
    if count == 0:
        return []
        
    return struct.unpack(f'<{count}h', data)

def classify(date=None, until=None):
    print("Classification worker started")

    while until is None or datetime.now() < until:
        time.sleep(ML_INTERVAL)

        # 1. Get Cleaned Data from Buffer
        times, voltages = live_buffer.get_snapshot()

        if times is None or voltages is None:
            continue

        df = pd.DataFrame({
            'datetime': times,
            'voltage': voltages
        })

        time_array = df['datetime'].values
        voltage_array = df['voltage'].values
        first_ts = df['datetime'].iloc[0]

        snippet = process_window(time_array, voltage_array, first_ts, 30)

        if snippet is None:
            continue

        history = history_buffer.get_data()
        history_buffer.add_data(snippet)
        snippet = history + [snippet]
        
        snippet = pd.DataFrame(snippet).drop(columns=['sleep_state'], errors='ignore')
        snippet = add_history_features(snippet)
        
        classification = classify_snippet(snippet)
        timestamp = datetime.now()

        classify_history_buffer.add_data((timestamp, classification))

        # result_queue.put({
        #     "timestamp": timestamp,
        #     "state": classification
        # })
        
        # print(f"Classified state: {classification} at {timestamp}")

        if date:
                file_exists = os.path.isfile(f"Data/{date}/classification-{date}.csv")

                processed_df = pd.DataFrame([{
                    'timestamp': time_array[0],
                    'classification': classification
                }])
                
                processed_df.to_csv(
                    f"Data/{date}/classification-{date}.csv", 
                    mode='a', 
                    header=not file_exists, 
                    index=False
                )

def start_workers(date,until=None):
    if date:
        if not os.path.exists(f"Data/{date}"):
            os.makedirs(f"Data/{date}")

        args = (date, until)
    else:
        args = ()
    classify_thread = threading.Thread(target=classify, args=args, daemon=True)
    classify_thread.start()

def run(date=None, until=None):
    print(f"Starting classification workers..., date: {date}")
    start_workers(date, until)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*1024*1024)
    sock.bind((UDP_IP, UDP_PORT_CAPACITANCE))
    sock.settimeout(2.0)

    print(f"Listening on {UDP_IP}:{UDP_PORT_CAPACITANCE}...")

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

                if len(local_accumulator) >= BATCH_THRESHOLD:
                    
                    try:
                        processed_df = data_processor.process_batch(local_accumulator)
 
                        if processed_df is not None and not processed_df.empty:
                            live_buffer.add_batch(processed_df)
                            
                    except Exception as e:
                        print(f"Error processing batch: {e}")

                    local_accumulator.clear()
            
            except socket.timeout:
                if not first_packet: print("No data...")
                continue

    except KeyboardInterrupt:
        print("\nStopping...")
        sock.close()

if __name__ == "__main__":
    run()