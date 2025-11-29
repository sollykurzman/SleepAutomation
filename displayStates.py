import pandas as pd
import plotly.express as px
import os

# ---------------------------------------------------------
# 1. USER CONFIGURATION
# ---------------------------------------------------------
# Enter the relative path to your CSV file here.
DATE = "281125"
FILE_PATH = f"Data/{DATE}/classification-{DATE}.csv"

# ---------------------------------------------------------
# 2. LOAD DATA
# ---------------------------------------------------------
if os.path.exists(FILE_PATH):
    print(f"Loading data from: {FILE_PATH}")
    df = pd.read_csv(FILE_PATH)
else:
    raise FileNotFoundError(f"File '{FILE_PATH}' not found. Please check the path.")

# ---------------------------------------------------------
# 3. DATA PROCESSING
# ---------------------------------------------------------

# Parse Timestamp
# Use format='mixed' to handle cases with and without milliseconds (e.g., "2025-11-23 00:47:21.320" vs "2025-11-24 23:44:51")
df['parsed_time'] = pd.to_datetime(df['timestamp'], format='mixed')

# Sort just in case the source data isn't perfectly ordered
df = df.dropna(subset=['parsed_time']).sort_values('parsed_time').reset_index(drop=True)

# ---------------------------------------------------------
# 4. CREATE BLOCKS (Intervals)
# ---------------------------------------------------------
intervals = []

if not df.empty:
    current_start = df.loc[0, 'parsed_time']
    current_state = df.loc[0, 'classification']

    for i in range(1, len(df)):
        row_time = df.loc[i, 'parsed_time']
        row_state = df.loc[i, 'classification']

        # If state changes, close the current block and start a new one
        if row_state != current_state:
            intervals.append({
                'State': current_state,
                'Start': current_start,
                'End': row_time
            })
            current_state = row_state
            current_start = row_time
    
    # Append the final block
    intervals.append({
        'State': current_state,
        'Start': current_start,
        'End': df.iloc[-1]['parsed_time']
    })

df_intervals = pd.DataFrame(intervals)

# ---------------------------------------------------------
# 5. VISUALIZATION
# ---------------------------------------------------------

# Define specific colors for your states
# These keys must match exactly what is in your 'classification' column
color_map = {
    "notInBed": "#d3d3d3",                  # Grey
    "inBed, Awake": "#ff7f50",              # Coral/Orange
    "inBed, Asleep, Core Sleep": "#0083fe", # Light Blue
    "inBed, Asleep, REM Sleep": "#70c4db",  # Medium Purple
    "inBed, Asleep, Deep Sleep": "#45237e"  # Dark Blue
}

# Define the explicit order for the Y-axis (Bottom to Top)
state_order = [
    "notInBed",
    "inBed, Awake",
    "inBed, Asleep, REM Sleep",
    "inBed, Asleep, Core Sleep",
    "inBed, Asleep, Deep Sleep"
]

# Create the Timeline
fig = px.timeline(
    df_intervals, 
    x_start="Start", 
    x_end="End", 
    y="State",        # Keep specific rows per state
    color="State", 
    color_discrete_map=color_map,
    category_orders={"State": state_order}, # Enforce the custom order
    title="Sleep Classification Timeline",
    height=400
)

# Customizing the layout
# fig.update_yaxes(autorange="reversed") # Removed to keep "Deep Sleep" (first item) at the bottom
fig.update_layout(
    xaxis_title="Time",
    yaxis_title="Sleep State",
    showlegend=True,
    template="plotly_white"
)

fig.show()