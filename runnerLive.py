#!/usr/bin/python3

import socket
import struct
import time
from datetime import datetime, timedelta
import threading

import storeData as store_data
import liveClassify as classifier
import processData as data_processor
from getCalendarData import get_calendar_data

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
PACKETS = 12
BUFFER_SIZE = 4096

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

if __name__ == "__main__":
    
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    night_id = datetime.now().strftime("%d%m%y")
    until = tomorrow.replace(hour=14, minute=00, second=0, microsecond=0)

    print(f"Running data collection and classification until {until} for night: {night_id}")

    events = get_calendar_data(tomorrow.replace(hour=00, minute=00, second=0, microsecond=0))

    events = sorted(events, key=lambda x: x['time'])

    events = [entry for entry in events if 'ignorethis' not in entry['notes']]

    print(events[0])

    # store_data.start_workers(night_id, until)

    # classifier.start_workers(night_id, until)

    # reciever_thread = threading.Thread(
    #     target=reciever,
    #     args=(until,),
    #     daemon=True
    # )
    # reciever_thread.start()