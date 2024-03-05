import pandas as pd
from datetime import datetime, timezone
import pytz

# Define the file path
file_path = "/home/its/IFSS/Tools/Report_Exports/schedule_2024_02_29.txt"

# Get current UTC date
current_utc_date = datetime.now(timezone.utc).date()
# Initialize an empty list to hold parsed data rows
parsed_data = []

# Open the file and process each line
with open(file_path, 'r') as file:
    lines = file.readlines()[15:]  # Skip the header lines

    for line in lines:
        if line.strip() == "":  # Stop if an empty line is encountered
            break
        if " y " in line:  # Check for 'y' in the "A" column
            parts = line.split()
            # Assuming the split() method sufficiently separates each piece of data into its correct column
            # If more sophisticated parsing is needed (e.g., handling date-times), additional processing will be required here
            parsed_data.append(parts)

# Assuming you've defined the correct columns based on your data's structure
columns = ["S", "M", "A", "SAT_NAME", "P", "O", "ST_DATE", "ST_TIME", "END_TIME", "DURATION", "INTERVAL", "SEL", "SAZ", "E_W", "MEL", "A_D", "EEL", "EAZ", "ORBIT"]

# Create a DataFrame from the parsed data
df = pd.DataFrame(parsed_data, columns=columns)

# Convert START and END columns to datetime objects

df["ST_DATE"] = pd.to_datetime(df["ST_DATE"], utc=True)
df["ST_DATE"] = df["ST_DATE"].dt.date

df["ST_TIME"] = pd.to_datetime(df["ST_TIME"], format='%H:%M:%S').dt.time
df["END_TIME"] = pd.to_datetime(df["END_TIME"], format='%H:%M:%S').dt.time

# Transform and rename columns as specified
df = df.rename(columns={
    "ORBIT": "ITEM",
    "SAT_NAME": "SAT",
    "A_D": "DIR",
    "MEL": "EL",
    "ST_DATE": "Start Date",
    "ST_TIME": "Start Time",
    "END_TIME": "End Time",
    "O": "OVR"
})

# Add a placeholder column for MODE if necessary, to be determined later
# df['MODE'] = 'Placeholder'

# Now filter by the current UTC date
df_filtered = df[df["Start Date"] == current_utc_date]

def determine_mode(start_time):
    hour = start_time.hour
    return 'Day' if 6 <= hour <= 18 else 'Night'

# # Apply MODE determination on the filtered DataFrame
df_filtered['MODE'] = df_filtered['Start Time'].apply(determine_mode)

# # Set IDLE to 1 for all rows in the filtered DataFrame
df_filtered['IDLE'] = 1

# # Final column selection and renaming for output
df_output = df_filtered[['ITEM', 'SAT', 'DIR', 'EL', 'MODE', 'Start Date', 'Start Time', 'End Time', 'OVR', 'IDLE']].copy()

# Specify the output file path
output_file_path = "/home/its/IFSS/Tools/Report_Exports/export.csv"

# Export df_output to CSV
df_output.to_csv(output_file_path, index=False)

print(f"Data exported successfully to {output_file_path}")