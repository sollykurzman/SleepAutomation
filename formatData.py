#!/usr/bin/python3

import pandas as pd
import numpy as np
from joblib import Parallel, delayed
import time
from scipy.fft import fft
from scipy.stats import entropy
import glob
import os
from tqdm import tqdm
import scipy.signal as signal

STEP_SIZE = 5
WINDOW_SIZE = 30
REFORMAT = False

def is_int(val):
    try:
        int(val)
        return True
    except ValueError:
        return False
    except TypeError:
        return False

def clean_signal(voltage_win):
    v_ac = voltage_win - np.median(voltage_win)
    return v_ac

def remove_drift(voltage_win, fs, cutoff=0.05):
    sos = signal.butter(2, cutoff, btype='high', fs=fs, output='sos')
    v_detrended = signal.sosfiltfilt(sos, voltage_win)
    return v_detrended

def smooth_signal(voltage_win, fs):
    win_size = int(fs * 0.5)
    voltage_smoothed = pd.Series(voltage_win).rolling(
        window=win_size, center=True, min_periods=1
    ).mean().to_numpy()
    return voltage_smoothed

def add_history_features(df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    cols_to_roll = ['variance', 'entropy', 'power', 'movement', 'breathrate', 'heartrate', 'heart_coherence', 'breath_coherence']
    
    for col in cols_to_roll:
        if col in df.columns:
            df[f'rolling_{col}'] = df[col].rolling(window=12, min_periods=1).mean()

    cols_to_diff = ['heartrate', 'breathrate', 'movement']
    
    for col in cols_to_diff:
        if col in df.columns:
            df[f'{col}_change'] = df[col].diff().fillna(0).astype(float)

    return df
    
def compute_movement(voltage_win, fs, win_s=1.0, threshold_ratio=3.0):
    win = int(win_s * fs)
    if win < 1:
        win = 1
    
    y2 = voltage_win ** 2
    kernel = np.ones(win) / win
    energy = np.convolve(y2, kernel, mode='same')
    
    baseline = np.median(energy)
    ratio = energy / (baseline + 1e-12)
    
    movement_flag = ratio > threshold_ratio
    return movement_flag.mean()

def get_breathrate_stats(voltage_win, fs):
    lowcut = 0.1
    highcut = 0.5
    dynamic_prominence_percentile = 75
    
    sos = signal.butter(4, [lowcut, highcut], btype='band', fs=fs, output='sos')
    
    filtered_voltage = signal.sosfiltfilt(sos, voltage_win)

    distance = fs / 1.5 
    
    dynamic_prominence = np.percentile(np.abs(filtered_voltage), dynamic_prominence_percentile)

    filtered_voltage = smooth_signal(filtered_voltage, fs)
    
    peaks, properties = signal.find_peaks(
        filtered_voltage, 
        distance=distance,
        prominence=dynamic_prominence 
    )

    if len(peaks) < 3:
        return None

    ibi_samples = np.diff(peaks)
    ibi_seconds = ibi_samples / fs
    
    instant_breathrate = 60.0 / ibi_seconds

    avg_breathrate = np.mean(instant_breathrate)
    std_breathrate = np.std(instant_breathrate)

    if avg_breathrate == 0:
        return None

    cv = std_breathrate / avg_breathrate
    
    breath_coherence = 1.0 / (cv + 1e-10)

    return avg_breathrate, breath_coherence

def get_heartbeat_stats(voltage_win, fs):
    lowcut = 0.7
    highcut = 2.5
    dynamic_prominence_percentile = 90
    
    sos = signal.butter(4, [lowcut, highcut], btype='band', fs=fs, output='sos')
    
    filtered_voltage = signal.sosfiltfilt(sos, voltage_win)

    distance = fs / 2.5 
    
    dynamic_prominence = np.percentile(np.abs(filtered_voltage), dynamic_prominence_percentile)
    
    peaks, properties = signal.find_peaks(
        filtered_voltage, 
        distance=distance,
        prominence=dynamic_prominence 
    )

    if len(peaks) < 3:
        return None

    ibi_samples = np.diff(peaks)
    ibi_seconds = ibi_samples / fs
    
    instant_bpms = 60.0 / ibi_seconds

    avg_bpm = np.mean(instant_bpms)
    std_bpm = np.std(instant_bpms)

    if avg_bpm == 0:
        return None

    cv = std_bpm / avg_bpm
    
    heart_coherence = 1.0 / (cv + 1e-10)

    return avg_bpm, heart_coherence

def load_sleep_state_data(night_id):
    csv_filepath = f'Data/{night_id}/true_watch_sleep_data-{night_id}.csv'
    user_input_path = f'Data/{night_id}/bedState_events-{night_id}.csv'
    
    df = pd.read_csv(csv_filepath)
    df = df[df['sleep_state'] != 'Disturbance'].reset_index(drop=True)
    
    df['start_datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], errors='coerce')
    df['end_datetime'] = pd.to_datetime(df['date'] + ' ' + df['end_time'], errors='coerce')
    
    midnight_crossover = df['end_datetime'] < df['start_datetime']
    df.loc[midnight_crossover, 'end_datetime'] += pd.Timedelta(days=1)
    
    df = df.dropna(subset=['start_datetime', 'end_datetime'])
    
    user_df = pd.DataFrame()
    if os.path.isfile(user_input_path):
        user_df = pd.read_csv(user_input_path)
        
        if 'datetime' in user_df.columns and 'sleep_state' in user_df.columns:
            user_df['start_datetime'] = pd.to_datetime(user_df['datetime'], errors='coerce')
            user_df = user_df.dropna(subset=['start_datetime'])
            
            user_df['end_datetime'] = user_df['start_datetime'].shift(-1)
            
            if not user_df.empty:
                user_df.loc[user_df.index[-1], 'end_datetime'] = user_df['start_datetime'].iloc[-1] + pd.Timedelta(days=1)
            
            user_crossover = user_df['end_datetime'] < user_df['start_datetime']
            user_df.loc[user_crossover, 'end_datetime'] += pd.Timedelta(days=1)
    
    first_in_bed_time = df['start_datetime'].min()
    first_row_awake = df.iloc[0]['sleep_state'] == 'Awake' if not df.empty else False
    
    return df, user_df, first_in_bed_time, first_row_awake

def assign_sleep_states(data_df, night_id):
    if not is_int(night_id):
        data_df['sleep_state'] = night_id
        return data_df

    watch_df, user_df, first_in_bed_time, first_row_awake = load_sleep_state_data(night_id)
        
    def get_state_for_timestamp(ts):
        match = watch_df[(ts >= watch_df['start_datetime']) & (ts < watch_df['end_datetime'])]
        if not match.empty:
            return match.iloc[0]['sleep_state']
        
        if not user_df.empty:
            user_match = user_df[(ts >= user_df['start_datetime']) & (ts < user_df['end_datetime'])]
            if not user_match.empty:
                return user_match.iloc[0]['sleep_state']
        
        if ts < first_in_bed_time and first_row_awake:
            return 'notInBed'
        
        return None
    
    data_df['sleep_state'] = data_df['timestamp'].apply(get_state_for_timestamp)
    return data_df

def calculate_window_frequency(time_win):
    time_diffs = pd.Series(time_win).diff().dropna()
    avg_diff = time_diffs.mean().total_seconds()
    fs = 1.0 / avg_diff
    return fs

def calculate_spectral_entropy(voltage_window):
    n = len(voltage_window)
    yf = np.abs(fft(voltage_window))[:n // 2]
    power_spectrum = np.square(yf)
    total_power = np.sum(power_spectrum) + 1e-10
    power_distribution = power_spectrum / total_power
    spectral_entropy = entropy(power_distribution, base=2)
    return spectral_entropy

def process_window(time_array, voltage_array, start_time, window_size):
    """Process a single window - NO sleep state assignment here"""
    end_time = start_time + pd.Timedelta(seconds=window_size)
    
    start_dt64 = np.datetime64(start_time)
    end_dt64 = np.datetime64(end_time)
    
    start_idx = np.searchsorted(time_array, start_dt64, side='left')
    end_idx = np.searchsorted(time_array, end_dt64, side='left')
    
    time_win = time_array[start_idx:end_idx]
    voltage_win = voltage_array[start_idx:end_idx]

    if voltage_win.size == 0 or time_win.size == 0: 
        return None

    MIN_FILTER_SAMPLES = 27
    if voltage_win.size <= MIN_FILTER_SAMPLES:
        return None

    fs = calculate_window_frequency(time_win)

    voltage_win = clean_signal(voltage_win)
    voltage_win = remove_drift(voltage_win, fs)

    window_variance = np.std(voltage_win)
    window_entropy = calculate_spectral_entropy(voltage_win)
    window_power = np.mean(np.square(voltage_win))

    movement = compute_movement(voltage_win, fs)

    breathrate = None
    breath_coherence = None
    heartrate = None
    heart_coherence = None

    breath_stats = get_breathrate_stats(voltage_win, fs)
    if breath_stats is not None:
        breathrate, breath_coherence = breath_stats

    heart_stats = get_heartbeat_stats(voltage_win, fs)
    if heart_stats is not None:
        heartrate, heart_coherence = heart_stats

    return {
        'timestamp': start_time,
        'variance': window_variance,
        'entropy': window_entropy,
        'power': window_power,
        'movement': movement,
        'breathrate': breathrate,
        'heartrate': heartrate,
        'heart_coherence': heart_coherence,
        'breath_coherence': breath_coherence
    }

def run(reformat=REFORMAT):
    print(f"Starting data formatting..., reformat={reformat}")
    dataframes = sorted(glob.glob(os.path.join('Data', '*', 'raw_data-*.csv')))
    all_nights_data = []

    for df_path in tqdm(dataframes, desc="Processing nights"):
        night_id = os.path.basename(df_path).split('-')[-1].replace('.csv', '')

        if os.path.isfile(f"Data/{night_id}/formatted_data-{night_id}.csv") and reformat == False:
            print(f"The file formatted_data-{night_id}.csv exists.")
            continue

        df = pd.read_csv(df_path, parse_dates=['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        
        time_array = df['datetime'].values
        voltage_array = df['voltage'].values

        first_ts = df['datetime'].iloc[0]
        last_ts = df['datetime'].iloc[-1]

        timestamp_list = pd.date_range(start=first_ts, end=last_ts, freq=f'{STEP_SIZE}s')

        formatted_data = Parallel(n_jobs=-1)(
            delayed(process_window)(time_array, voltage_array, ts, WINDOW_SIZE) 
            for ts in tqdm(timestamp_list, desc=f"Processing Night {night_id}", leave=False)
        )
        formatted_data = [data for data in formatted_data if data is not None]

        data = pd.DataFrame(formatted_data)
        data = data.sort_values(by='timestamp')
        data = data.reset_index(drop=True)

        if data is not None:
            data = add_history_features(data)
            data = assign_sleep_states(data, night_id)
            all_nights_data.append(data)

        print(f"Writing formatted_data-{night_id}.csv...")
        data.to_csv(f'Data/{night_id}/formatted_data-{night_id}.csv', index=False)

    if reformat:
        if all_nights_data:
            print("Writing over all_nights_formatted_data.csv...")
            all_nights_data = pd.concat(all_nights_data, ignore_index=True)
            all_nights_data.to_csv('Data/all_nights_formatted_data.csv', index=False)
        else:
            print("No data was processed.")
    else:
        if all_nights_data:
            print("Adding data to all_nights_formatted_data.csv...")
            all_nights_data = pd.concat(all_nights_data, ignore_index=True)
            all_nights_data.to_csv('Data/all_nights_formatted_data.csv', mode='a', index=False, header=False)
        else:
            print("No new nights were processed.")

if __name__ == "__main__":
    run()