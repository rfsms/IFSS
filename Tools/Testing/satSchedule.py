import http.client
from datetime import datetime, timedelta
import logging
from pymongo import MongoClient
import csv
import re

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
satSchedule = db["testSatSchedule"]

# # Reset the Root Logger and seup logging
# for handler in logging.root.handlers[:]:
#     logging.root.removeHandler(handler)
# logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

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

    excluded_satellites = ["TERRA", "JPSS1", "NOAA 21", "AQUA", "NPP", "GCOM-W1"]

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
                
                todaysDate = datetime.utcnow().strftime('%d-%b-%Y')  # Format for matching in the document
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
                output_path = "/home/noaa_gms/IFSS/Tools/Report_Exports/testSchedule.csv"
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


fetchReport()