import schedule
import http.client
from datetime import datetime, timedelta, timezone
import logging
from time import sleep
from pymongo import MongoClient
import IFSS_RSA
import csv
import re
import pandas as pd

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
satSchedule = db["satSchedule"]

# Reset the Root Logger and seup logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/its/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Fetch report is done daily using schedule at 00:06 UTC 
# since AOML/IRC all run cronjobs @ 00:05UTC for 48 hour window schedules)  
def fetchReport():
    '''
    Designed to fetch satellite schedule data from a selected earth station EOS-FES, 
    parse the data to filter records for the current day since the schedule is a 48 hour window, 
    and then insert the records into a MongoDB db ('ifss') collection ('satSchedule').

    Sample Data vs regex (parts[])
    
    ITEM  SAT                  DIR  EL  MODE   START                 END                   OVR  IDLE
    ------------------------------------------------------------------------------------------------
    174473 NOAA 21              N    28  DAY    16-Feb-2024 00:20:43  16-Feb-2024 00:32:48  0    1

    (\d+) captures 174473 (item)
    ([\w\s-]+) captures NOAA 21 (satellite name, sat)
    (\w) captures N (direction, dir)
    (\d+) captures 28 (elevation, el)
    (\w) captures DAY (mode)
    (\d+-\w+-\d+) captures 16-Feb-2024 (start date)
    (\d+:\d+:\d+) captures 00:20:43 (start time)
    (\d+-\w+-\d+) captures 16-Feb-2024 (end date)
    (\d+:\d+:\d+) captures 00:32:48 (end time)
    (\d+) captures 0 (over, ovr)
    (\d+) captures 1 (idle)
    '''

    # excluded_satellites = ["TERRA", "JPSS1", "NOAA 21", "AQUA", "NPP", "GCOM-W1"]
    excluded_satellites = []

    try:
        now = datetime.utcnow()
        start_of_today = datetime(now.year, now.month, now.day)
        end_of_today = start_of_today + timedelta(days=1)
        
        # Determine if a schedule for today already exists
        schedule_exists = satSchedule.find_one({"timestamp": {"$gte": start_of_today, "$lt": end_of_today}}) is not None

        if not schedule_exists:
            logging.info("fetchReport() No schedule data available for today, fetching new schedule.")
            
            # Establish HTTP connection and request the schedule
            conn = http.client.HTTPSConnection("dbps.aoml.noaa.gov", 443)
            conn.request("GET", "/scheduled_received/schedule.txt")
            response = conn.getresponse()

            if response.status == 200:
                data = response.read().decode('utf-8')
                lines = data.splitlines()
                
                todaysDate = datetime.utcnow().strftime('%d-%b-%Y')
                rows = []

                # Process each line of the fetched data
                for line in lines:
                    match = re.match(r"(\d+)\s+([\w\s-]+)\s+(\w)\s+(\d+)\s+(\w+)\s+(\d+-\w+-\d+)\s+(\d+:\d+:\d+)\s+(\d+-\w+-\d+)\s+(\d+:\d+:\d+)\s+(\d+)\s+(\d+)", line)
                    if match:
                        parts = match.groups()
                        #Exclude sats here and skip line if {excluded_satellites} found
                        satellite_name = parts[1].strip()
                        # Otherwise continue processing schedule
                        if satellite_name in excluded_satellites:
                            continue
                        startDate = parts[5]
                        if startDate == todaysDate:
                            record = {
                                "item": parts[0],
                                "sat": parts[1].strip(),
                                "dir": parts[2],
                                "el": int(parts[3]),
                                "mode": parts[4],
                                "startDate": parts[5],
                                "startTime": parts[6],
                                "endDate": parts[7],
                                "endTime": parts[8],
                                "ovr": int(parts[9]),
                                "idle": int(parts[10])
                            }
                            rows.append(record)

                # Sort the schedule entries by start time
                rows.sort(key=lambda x: x['startTime'])

                # Write the schedule to a CSV file
                output_path = "/home/its/IFSS/Tools/Report_Exports/schedule.csv"
                with open(output_path, 'w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(["ITEM", "SAT", "DIR", "EL", "MODE", "Start Date", "Start Time", "End Date", "End Time", "OVR", "IDLE"])
                    for row in rows:
                        writer.writerow([row["item"], row["sat"], row["dir"], row["el"], row["mode"],
                                         row["startDate"], row["startTime"], row["endDate"], row["endTime"],
                                         row["ovr"], row["idle"]])

                # Insert the processed data into MongoDB
                document = {
                    "timestamp": datetime.utcnow(),
                    "schedule": rows
                }
                satSchedule.insert_one(document)
                logging.info('New schedule extracted, logged, and inserted into MongoDB.')
            else:
                logging.error(f"Failed to fetch schedule: {response.status}, {response.reason}")
        else:
            logging.info("fetchReport() Schedule data for today already exists in the database.")


    except Exception as e:
        logging.info(f'An error occurred in fetchReport(): {e}')

    # Call IFSS_RSA.main() outside the try-except block to ensure it's called in all scenarios
    logging.info('Attempting to call IFSS_RSA.main()')
    try:
        IFSS_RSA.main()  # Ensure this is the correct call
        logging.info('IFSS_RSA.main() called successfully')
    except Exception as e:
        logging.error(f'Failed to call IFSS_RSA.main(): {e}')

def fetchTMTR_Report():
        try:
            now = datetime.utcnow()
            start_of_today = datetime(now.year, now.month, now.day)
            end_of_today = start_of_today + timedelta(days=1)

            # Determine if a schedule for today already exists
            schedule_exists = satSchedule.find_one({"timestamp": {"$gte": start_of_today, "$lt": end_of_today}}) is not None

            if not schedule_exists:
                logging.info("fetchReport() No schedule data available for today, fetching new schedule.")
                
                # Define the file path
                file_path = "/home/its/IFSS/Tools/Report_Exports/schedule_2024_02_29.txt"
                output_file_path = "/home/its/IFSS/Tools/Report_Exports/schedule.csv"

                # Read the file, skipping initial header lines and stopping at the first empty line
                df = pd.read_csv(file_path, skiprows=15, delim_whitespace=True, comment='\n', header=None)

                # Filter rows where 'y' is present in the third column (assuming 0-based indexing for columns)
                df = df[df.iloc[:, 2].str.contains('y', na=False)]

                # Define and assign column names
                columns = ["S", "M", "A", "SAT", "P", "OVR", "Start Date", "Start Time", "End Time", "DURATION", "INTERVAL", "SEL", "SAZ", "E_W", "EL", "DIR", "EEL", "EAZ", "ITEM"]
                df.columns = columns
                
                # Set 'End Date' to 'ST_DATE'
                df['End Date'] = df['Start Date']

                # Convert 'ST_TIME' and 'END_TIME' properly to ensure they are datetime.time objects
                df['Start Time'] = pd.to_datetime(df['Start Time'], format='%H:%M:%S').dt.time

                # Correctly convert 'END_TIME' to datetime for comparison and adjust if necessary
                df['End Time'] = pd.to_datetime(df['End Time'], format='%H:%M:%S', errors='coerce')
                df['END_TIME_ADJUSTED'] = df['End Time'].apply(lambda x: x.time().replace(hour=23, minute=59, second=59) if x.time() > datetime.strptime("23:59:59", '%H:%M:%S').time() else x.time())
               
                # Now, use 'END_TIME_ADJUSTED' for further processing and drop the adjustment column if no longer needed
                df['End Time'] = df['END_TIME_ADJUSTED']
                df.drop('END_TIME_ADJUSTED', axis=1, inplace=True)

                def determine_mode(start_time):
                    hour = pd.to_datetime(start_time, format='%H:%M:%S').time().hour
                    return 'Day' if 6 <= hour <= 18 else 'Night'


                # Filter by the current UTC date
                current_utc_date = datetime.now(timezone.utc).date()
                #Works
                df['Start Date'] = pd.to_datetime(df['Start Date'], utc=True).dt.date
                df = df[df["Start Date"] == current_utc_date]

                df['MODE'] = df['Start Time'].astype(str).apply(determine_mode)
                df['IDLE'] = 1

                # Final column selection and renaming for output
                columns_final = ['ITEM', 'SAT', 'DIR', 'EL', 'MODE', 'Start Date', 'Start Time', 'End Date', 'End Time', 'OVR', 'IDLE']
                df_output = df[columns_final].copy()

                # Export to CSV with uppercase headers, ensuring columns are in the correct order
                df_output.to_csv(output_file_path, index=False)

                logging.info(f"Data exported successfully to {output_file_path}")

                # Convert date and time columns to string format
                df_output['Start Date'] = df_output['Start Date'].astype(str)
                df_output['Start Time'] = df_output['Start Time'].apply(lambda x: x.strftime('%H:%M:%S') if pd.notnull(x) else '')
                df_output['End Time'] = df_output['End Time'].apply(lambda x: x.strftime('%H:%M:%S') if pd.notnull(x) else '')
                df_output['End Date'] = df_output['End Date'].astype(str)

               # Renaming columns for MongoDB insertion, making sure the names are lowercase and replacing spaces with underscores
                df_output.rename(columns={
                    'ITEM': 'item', 
                    'SAT': 'sat', 
                    'DIR': 'dir', 
                    'EL': 'el', 
                    'MODE': 'mode', 
                    'Start Date': 'startDate', 
                    'Start Time': 'startTime', 
                    'End Date': 'endDate', 
                    'End Time': 'endTime', 
                    'OVR': 'ovr', 
                    'IDLE': 'idle'
                }, inplace=True)

                # Convert DataFrame to a list of dictionaries
                records = df_output.to_dict('records')
                
                # Prepare the document for MongoDB
                document = {
                    "timestamp": datetime.utcnow(),
                    "schedule": records
                }

                satSchedule.insert_one(document)
                logging.info('New schedule extracted, logged, and inserted into MongoDB.')
            else:
                logging.info("fetchReport() Schedule data for today already exists in the database.")

        except Exception as e:
            logging.info(f'An error occurred in fetchReport(): {e}')

        # Call IFSS_RSA.main() outside the try-except block to ensure it's called in all scenarios
        logging.info('Attempting to call IFSS_RSA.main()')
        try:
            IFSS_RSA.main()  # Ensure this is the correct call
            logging.info('IFSS_RSA.main() called successfully')
        except Exception as e:
            logging.error(f'Failed to call IFSS_RSA.main(): {e}')

schedule.every().day.at("00:06").do(fetchTMTR_Report)

fetchTMTR_Report()

while True:
    schedule.run_pending()
    sleep(1)
    
