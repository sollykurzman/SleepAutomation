#!/usr/bin/python3

import socket
import struct
import time
import os
from datetime import datetime
import threading
from collections import deque
import pandas as pd

import processData as data_processor

DATE = "Awake"
UDP_IP = "0.0.0.0"
UDP_PORT_CAPACITANCE = 5005
UDP_PORT_STATE = 5006
BUFFER_SIZE = 4096
PACKETS = 12
ML_INTERVAL = 2.0
STORE_CLASSIFICATION = False

write_queue = deque(maxlen=200000)
write_lock = threading.Lock()

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

#Create Buffer Instance
live_buffer = RollingBuffer(window_seconds=30, sample_rate=100)

def store_data(date, until=None):
    print("Processing worker started")
    accumulator = []

    while until is None or datetime.now() < until:
        new_data_batch = []
        with write_lock:
            if write_queue:
                new_data_batch = list(write_queue)
                write_queue.clear()

        if new_data_batch:
            accumulator.extend(new_data_batch)
        
        if len(accumulator) >= (50 * PACKETS):
            batch = list(accumulator)
            accumulator.clear()

            try:
                processed_df = data_processor.process_batch(batch)
        
                if processed_df is not None and not processed_df.empty:
                    live_buffer.add_batch(processed_df)

                    file_exists = os.path.isfile(f"Data/{date}/raw_data-{date}.csv")

                    processed_df.to_csv(
                        f"Data/{date}/raw_data-{date}.csv", 
                        mode='a', 
                        header=not file_exists, 
                        index=False
                    )

            except Exception as e:
                print(f"Error in processing: {e}")

        elif not new_data_batch:
            time.sleep(0.01)

def monitor_switch_events(date, until=None):
    print(f"Switch Monitor worker started on port {UDP_PORT_STATE}")
    
    sock_switch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_switch.bind((UDP_IP, UDP_PORT_STATE))
    
    dir_path = f"Data/{date}"
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    prev = ""
        
    while until is None or datetime.now() < until:
        try:
            data, addr = sock_switch.recvfrom(1024)
            message = data.decode('utf-8').strip()
            timestamp = time.time()
            readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')

            if message != prev:
                prev = message
            
                print(f"Switch Event Received: {message} from {addr}")
                
                file_path = f"{dir_path}/bedState_events-{date}.csv"
                file_exists = os.path.isfile(file_path)
                
                df_switch = pd.DataFrame([{
                    'datetime': readable_time,
                    'sleep_state': message
                }])
                
                df_switch.to_csv(
                    file_path,
                    mode='a',
                    header=not file_exists,
                    index=False
                )
            
        except Exception as e:
            print(f"Error in switch monitor: {e}")

def parse_packet(data):
    remainder = len(data) % 2
    if remainder != 0:
        data = data[:-remainder] 
        
    count = len(data) // 2
    if count == 0:
        return []
        
    return struct.unpack(f'<{count}h', data)

def start_workers(date, until=None):
    if not os.path.exists(f"Data/{date}"):
        os.makedirs(f"Data/{date}")

    args = (date, until)
    
    data_thread = threading.Thread(target=store_data, args=args, daemon=True)
    data_thread.start()

    switch_thread = threading.Thread(target=monitor_switch_events, args=args, daemon=True)
    switch_thread.start()

def run(date, until=None):
    start_workers(date, until)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*1024*1024)
    sock.bind((UDP_IP, UDP_PORT_CAPACITANCE))
    sock.settimeout(2.0)
    
    print(f"Listening on {UDP_IP}:{UDP_PORT_CAPACITANCE}...")
    
    first_packet = True
    
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

                with write_lock:
                    write_queue.extend(new_entries)
                
            except socket.timeout:
                if not first_packet: print("No data...")
                continue
                
    except KeyboardInterrupt:
        print("\nStopping...")
        sock.close()

if __name__ == "__main__":
    run(DATE)