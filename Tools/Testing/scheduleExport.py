import pandas as pd
from datetime import datetime, timezone, timedelta
import logging
from pymongo import MongoClient

# Reset the Root Logger and seup logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/its/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
satSchedule = db["satSchedule"]

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

fetchTMTR_Report()