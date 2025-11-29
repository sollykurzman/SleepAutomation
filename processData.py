#!/usr/bin/python3

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt

TARGET_SAMPLE_RATE = 100
ANTIALIASING_CUTOFF = 45.0
FILTER_ORDER = 5
VOLTAGE_SCALE = 0.125 / 1000.0


def redistribute_timestamps_linear(df):
    unique_timestamps = df['timestamp_unix'].unique()
    
    if len(unique_timestamps) < 2:
        return df

    avg_gap = np.mean(np.diff(unique_timestamps))

    new_rows = []
    
    grouped = df.groupby('timestamp_unix')
    
    for i, ts in enumerate(unique_timestamps):
        group = grouped.get_group(ts)
        n_samples = len(group)
        
        if i < len(unique_timestamps) - 1:
            next_ts = unique_timestamps[i+1]
            time_gap = next_ts - ts
        else:
            time_gap = avg_gap

        if n_samples > 1:
            offsets = np.linspace(0, time_gap, n_samples, endpoint=False)
        else:
            offsets = np.array([0.0])

        current_data = group.copy()
        current_data['timestamp_unix'] = ts + offsets
        new_rows.append(current_data)

    if new_rows:
        return pd.concat(new_rows).reset_index(drop=True)
    return df

def process_batch(raw_batch):
    if not raw_batch:
        return None

    df = pd.DataFrame(raw_batch, columns=['timestamp_unix', 'adc_raw'])
    
    df['voltage'] = df['adc_raw'] * VOLTAGE_SCALE
    
    df = redistribute_timestamps_linear(df)
    
    time_span = df['timestamp_unix'].max() - df['timestamp_unix'].min()
    if time_span == 0: return None
    
    fs_est = len(df) / time_span

    if len(df) > FILTER_ORDER * 4:
        b, a = butter(FILTER_ORDER, ANTIALIASING_CUTOFF / (fs_est / 2), btype='low')
        try:
            df['voltage'] = filtfilt(b, a, df['voltage'].values)
        except Exception as e:
            print(f"Filter Error (skipping filter): {e}")
    
    df['datetime'] = pd.to_datetime(df['timestamp_unix'], unit='s')
    df = df.set_index('datetime')
    
    resample_interval = f"{1000 // TARGET_SAMPLE_RATE}ms"
    
    df_final = df['voltage'].resample(resample_interval).mean().dropna().reset_index()
    
    return df_final