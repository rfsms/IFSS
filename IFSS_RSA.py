import schedule
from time import sleep
from datetime import datetime
import logging
import json
from pymongo import MongoClient
import subprocess
import csv
import os

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
spectrumData = db["spectrumData"]
satSchedule = db["satSchedule"]
scheduleRun = db["scheduleRun"]

# Reset the Root Logger and seup logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

CSV_FILE_PATH = '/home/noaa_gms/IFSS/Tools/Report_Exports/schedule.csv'

def restart_service():
    try:
        logging.info("Attempting to restart IFSS.service")
        subprocess.run(['sudo', '/home/noaa_gms/IFSS/Tools/restart_IFSS.sh'], check=True)
        logging.info(f"Successfully requested restart IFSS.service.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to restart the IFSS.service: {e}")
    except Exception as e:
        logging.error(f"Unexpected error while restarting the IFSS.service: {e}")

def handle_pause(log_message, restart_message=None, sleep_time=5, loop_completed=None):
    log_flag = True
    was_paused = False
    while os.path.exists("/home/noaa_gms/RFSS/pause_flag.txt"):
        if log_flag:
            logging.info(log_message)
            log_flag = False
        was_paused = True
        sleep(sleep_time)
    
        if was_paused:
            logging("Instrument after pause successful")

            if restart_message:
                logging.info(restart_message)
            if loop_completed is not None:
                loop_completed[0] = False

        return was_paused

def process_schedule():
    logging.info("starting process schedule")
    """
    This function is the timing behind IFSS data capture.  Reads the CSV_FILE_PATH and goes through each row determining
    aos/los, etc and compares against current time.  If older entries exist continue, if current time meet aos time then 
    wait.  Once current time matches an aos, data is being captured until los.
    FOR MXA, between aos/los capture induvidual IQs send to Received from SA.  Finally after los, move Received/*.mat to toDemod for processing.
    """
    loop_completed = [True]

    with open(CSV_FILE_PATH, 'r') as csvfile:
        logging.info("opening csv file")
        csvreader = csv.reader(csvfile)
        next(csvreader)

        for row in csvreader:
            logging.info("csv file in process")
            handle_pause("Pause flag detected at start of row.", "Pause_flag removed. Restarting schedule...", loop_completed=loop_completed)

            # Investigate me
            if len(row) < 5:
                logging.info(f"End of rows in schedule")
                continue

            aos_time = datetime.strptime(row[6], '%H:%M:%S').time()
            los_time = datetime.strptime(row[8], '%H:%M:%S').time()

            satellite_name = row[1]
            now = datetime.utcnow().time()
            
            print(f'AOS: {aos_time}')
            print(f'lOS: {los_time}')

            # If current time has already passed the scheduled los_datetime, skip to the next schedule
            if now > los_time:
                continue

            # If current time is before the scheduled aos_time, wait until aos_time is reached
            while now < aos_time:
                logging.info("now < aos_time")
                handle_pause("Pause flag detected. Pausing pass schedule.", "Pause_flag removed. Restarting schedule...", sleep_time=1, loop_completed=loop_completed)
                now = datetime.utcnow().time()
                sleep(1)

            # Adding a trigger to provide single hit log and start running
            triggered = False

            #Between AOL/LOS time
            while True:
                handle_pause("Schedule paused. Waiting for flag to be removed.", "Pause_flag removed. Restarting schedule...", loop_completed=loop_completed)
                now = datetime.utcnow().time()
                if now >= los_time:
                    break
                    
                if not triggered:
                    print(f'Current scheduled row under test: {row}')
                    triggered = True

                    # Insert the data into MongoDB as a single document
                    document = {
                        "timestamp": datetime.utcnow(),
                        "row": row,
                        }
                    scheduleRun.insert_one(document)
                
                # Intrumentation happens here
                logging.info("doing instruemtnstuff")
                sleep(1)
            
            # Only execute this part if the loop was not broken by the pause flag
            if loop_completed[0]:  # Check if loop completed successfully
                document_update = {
                    "$set": {
                        "processed": "true"  # Set processed to "true" as the loop completed successfully
                    }
                }
                scheduleRun.update_one({"timestamp": document["timestamp"]}, document_update)
                logging.info("Scheduled row completed successfully!")
            else:
                document_update = {
                    "$set": {
                        "processed": "false"  # Set processed to "false" as the loop did not complete successfully
                    }
                }
                scheduleRun.update_one({"timestamp": document["timestamp"]}, document_update)
                logging.info("Scheduled row encountered errors.")

def main():
    logging.info("Starting IFSS_RSA main routine")

    # Instrumentat setup here

    try:
        process_schedule()
        logging.info("Schedule finished for the day.\n")
    except Exception as e:
        logging.info(f"An error occurred in RFSS_PXA.py main(): {e}")
        restart_service()

if __name__ == "__main__":
    try:    
        main()
    except Exception as e:
        logging.error(f"An error occurred in RFSS_PXA.py: {e}")