#!/usr/bin/env python3
"""
High-speed UDP data receiver for Raspberry Pi 5
Stores timestamp + ADC value in binary format
"""

import socket
import struct
import time
import os
from datetime import datetime
import threading
from collections import deque

# Configuration
UDP_IP = "0.0.0.0"
UDP_PORT = 5005
BUFFER_SIZE = 4096
DATA_DIR = "adc_data-2021"
SAMPLES_PER_FILE = 1000000

# Shared state
write_queue = deque(maxlen=200000)
write_lock = threading.Lock()
stats = {
    'total_samples': 0,
    'samples_per_second': 0,
    'bytes_written': 0,
    'last_stats_time': time.time()
}


def ensure_data_directory():
    """Create data directory if needed"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def get_filename():
    """Generate timestamped filename"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(DATA_DIR, f"adc_data_{timestamp}.bin")


def format_bytes(num_bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def write_worker():
    """Background thread that writes data to disk"""
    current_file = None
    file_handle = None
    sample_count = 0
    
    while True:
        # Get batch from queue
        with write_lock:
            if not write_queue:
                time.sleep(0.01)
                continue
            
            batch = [write_queue.popleft() 
                    for _ in range(min(5000, len(write_queue)))]
        
        # Open new file if needed
        if sample_count >= SAMPLES_PER_FILE or current_file is None:
            if file_handle:
                file_handle.close()
                size_mb = os.path.getsize(current_file) / (1024*1024)
                print(f"Closed: {os.path.basename(current_file)} ({size_mb:.1f} MB)")
            
            current_file = get_filename()
            file_handle = open(current_file, 'wb', buffering=8192*8)
            file_handle.write(struct.pack('<4sH', b'ADC2', 1))  # Header
            sample_count = 0
            print(f"Created: {os.path.basename(current_file)}")
        
        # Write batch to disk
        for timestamp, adc_value in batch:
            file_handle.write(struct.pack('<dh', timestamp, adc_value))
            stats['bytes_written'] += 10
        
        file_handle.flush()
        sample_count += len(batch)


def parse_packet(data):
    """Extract ADC values from ESP32 packet"""
    SAMPLE_SIZE = 2  # Just 2 bytes per sample now
    values = []
    
    for i in range(0, len(data), SAMPLE_SIZE):
        if i + SAMPLE_SIZE <= len(data):
            adc_value = struct.unpack('<h', data[i:i+SAMPLE_SIZE])[0]
            values.append(adc_value)
    
    return values


def print_stats(start_time):
    """Print current statistics"""
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)
    secs = int(elapsed % 60)
    
    queue_size = len(write_queue)
    rate = stats['samples_per_second']
    total = stats['total_samples']
    written = format_bytes(stats['bytes_written'])
    
    print(f"Current Time: {datetime.now()} | "
          f"Time Elapsed: {hours:02d}:{mins:02d}:{secs:02d} | "
          f"Rate: {rate:4d}/s | "
          f"Total: {total:9d} | "
          f"Queue: {queue_size:5d} | "
          f"Written: {written}")
    
    stats['samples_per_second'] = 0


def main():
    """Main receiver loop"""
    print("High-Speed ADC Data Receiver")
    print("Storage: 10 bytes per sample (Pi timestamp + ADC value)")
    print("Network: 2 bytes per sample from ESP32")
    print("-" * 60)
    
    ensure_data_directory()
    
    # Start background writer
    writer = threading.Thread(target=write_worker, daemon=True)
    writer.start()
    print("Background writer started")
    
    # Setup UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*1024*1024)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(2.0)
    print(f"Listening on {UDP_IP}:{UDP_PORT}")
    print("Waiting for ESP32...\n")
    
    first_packet = True
    start_time = time.time()
    
    try:
        while True:
            try:
                data, addr = sock.recvfrom(BUFFER_SIZE)
                
                if first_packet:
                    print(f"Connected to {addr[0]}:{addr[1]}\n")
                    first_packet = False
                    print_stats(start_time)
                
                timestamp = time.time()
                adc_values = parse_packet(data)
                
                # Add to write queue
                with write_lock:
                    for value in adc_values:
                        write_queue.append((timestamp, value))
                        stats['total_samples'] += 1
                        stats['samples_per_second'] += 1
                
                # Print stats every 5 seconds
                if time.time() - stats['last_stats_time'] >= 5.0:
                    print_stats(start_time)
                    stats['last_stats_time'] = time.time()
                
            except socket.timeout:
                if not first_packet:
                    print("No data for 2 seconds...")
                continue
                
    except KeyboardInterrupt:
        print("\n\nStopping receiver...")
        print(f"Total samples: {stats['total_samples']:,}")
        print(f"Total written: {format_bytes(stats['bytes_written'])}")
        print(f"Run time: {time.time() - start_time:.1f} seconds")
        sock.close()


if __name__ == "__main__":
    main()
