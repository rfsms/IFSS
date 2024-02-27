from ctypes import *
from RSA_API import *
import sys
from time import sleep
from datetime import datetime
import logging
from pymongo import MongoClient
import subprocess
import csv
import os

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/?replicaSet=rs0')
db = client["ifss"]
spectrumData = db["spectrumData"]
satSchedule = db["satSchedule"]
scheduleRun = db["scheduleRun"]

# Reset the Root Logger and seup logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

RTLD_LAZY = 0x0001
LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
rsa = CDLL("/home/noaa_gms/IFSS/Tools/lib/libRSA_API.so", LAZYLOAD)
usbapi = CDLL("/home/noaa_gms/IFSS/Tools/lib/libcyusb_shared.so", LAZYLOAD)

CSV_FILE_PATH = '/home/noaa_gms/IFSS/Tools/Report_Exports/schedule.csv'

################ RSA SETUP AND CONFIG ################
def err_check(rs):
    if ReturnStatus(rs) != ReturnStatus.noError:
        raise RSAError(ReturnStatus(rs).name)

def search_connect():
    numFound = c_int(0)
    intArray = c_int * DEVSRCH_MAX_NUM_DEVICES
    deviceIDs = intArray()
    deviceSerial = create_string_buffer(DEVSRCH_SERIAL_MAX_STRLEN)
    deviceType = create_string_buffer(DEVSRCH_TYPE_MAX_STRLEN)
    apiVersion = create_string_buffer(DEVINFO_MAX_STRLEN)

    rsa.DEVICE_GetAPIVersion(apiVersion)

    err_check(rsa.DEVICE_Search(byref(numFound), deviceIDs, deviceSerial, deviceType))

    if numFound.value < 1:
        logging.info('No instruments found. Exiting script.')
        sys.exit(0)
    elif numFound.value == 1:
        err_check(rsa.DEVICE_Connect(deviceIDs[0]))
    rsa.CONFIG_Preset()

def config_spectrum(cf=1e9, refLevel=0, span=40e6, rbw=300e3):
    rsa.SPECTRUM_SetEnable(c_bool(True))
    rsa.CONFIG_SetCenterFreq(c_double(cf))
    rsa.CONFIG_SetReferenceLevel(c_double(refLevel))

    rsa.SPECTRUM_SetDefault()
    specSet = Spectrum_Settings()
    rsa.SPECTRUM_GetSettings(byref(specSet))
    specSet.window = SpectrumWindows.SpectrumWindow_Hann
    specSet.verticalUnit = SpectrumVerticalUnits.SpectrumVerticalUnit_dBm
    specSet.span = span
    specSet.rbw = rbw
    rsa.SPECTRUM_SetSettings(specSet)
    rsa.SPECTRUM_GetSettings(byref(specSet))
    return specSet

def acquire_spectrum(specSet):
    ready = c_bool(False)
    traceArray = c_float * specSet.traceLength
    traceData = traceArray()
    outTracePoints = c_int(0)
    traceSelector = SpectrumTraces.SpectrumTrace1

    rsa.DEVICE_Run()
    rsa.SPECTRUM_AcquireTrace()
    while not ready.value:
        rsa.SPECTRUM_WaitForDataReady(c_int(100), byref(ready))
    rsa.SPECTRUM_GetTrace(traceSelector, specSet.traceLength, byref(traceData), byref(outTracePoints))
    rsa.DEVICE_Stop()
    
    # Convert C float array to Python list of floats...arggghhh
    return [float(traceData[i]) for i in range(specSet.traceLength)]

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
    while os.path.exists("/home/noaa_gms/IFSS/pause_flag.txt"):
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

def process_schedule(specSet, freq_list_mhz):
    """
    This function is the timing and capture behind IFSS code.  Connect to RSA360 and setup for capture. Then read the CSV_FILE_PATH and goes through each row determining
    aos/los, etc and compares against current time.  Three scenarios:
       * If older entries exist continue (skip)
       *  If current time matches an aos, data is being captured until los
        * If current time doesnt meet aos time then continue (wait for aos)
    """

    loop_completed = [True]

    with open(CSV_FILE_PATH, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        next(csvreader)
        logging.info("Opened csv file and started process_schedule()")

        for row in csvreader:
            handle_pause("Pause flag detected at start of row.", "Pause_flag removed. Restarting schedule...", loop_completed=loop_completed)

            # Investigate me
            if len(row) < 5:
                logging.info(f"End of rows in schedule")
                continue

            aos_time = datetime.strptime(row[6], '%H:%M:%S').time()
            los_time = datetime.strptime(row[8], '%H:%M:%S').time()

            now = datetime.utcnow().time()

            # If current time has already passed the scheduled los_datetime, skip to the next schedule
            if now > los_time:
                continue

            # If current time is before the scheduled aos_time, wait until aos_time is reached
            while now < aos_time:
                # logging.info("now < aos_time")
                handle_pause("Pause flag detected. Pausing pass schedule.", "Pause_flag removed. Restarting schedule...", sleep_time=1, loop_completed=loop_completed)
                now = datetime.utcnow().time()
                sleep(1)

            # Adding a trigger to provide single hit log and start running
            triggered = False

            #Between AOL/LOS time
            while True:
                # logging.info(f'Triggered: {triggered}')
                handle_pause("Schedule paused. Waiting for flag to be removed.", "Pause_flag removed. Restarting schedule...", loop_completed=loop_completed)
                
                now = datetime.utcnow().time()
                if now >= los_time:
                    break
                    
                if not triggered:
                    logging.info(f'Current scheduled row under test: {row}')
                    triggered = True

                    # Insert the schedule data into MongoDB as a single document
                    schedule_document = {
                        "timestamp": datetime.utcnow(),
                        "row": row,
                        }
                    insert_result = scheduleRun.insert_one(schedule_document)
                    document_id = insert_result.inserted_id
                
                # Intrumentation happens here
                trace = acquire_spectrum(specSet)
                currentTime = datetime.today().isoformat(sep=' ', timespec='milliseconds')

                # Create a document for MongoDB and insert into thew collection
                frequencies = {str(round(freq, 4)): float(value) for freq, value in zip(freq_list_mhz, trace)}
                document = {
                    "timestamp": currentTime,
                    "frequencies": frequencies
                }
                spectrumData.insert_one(document)
                sleep(1)
            
            # Updating scheduleRun after processing a row
            if loop_completed[0]:  # This block and the else block need adjustment
                document_update = {"$set": {"processed": "true"}}
                logging.info("Scheduled row completed successfully and database updated!")
            else:
                document_update = {"$set": {"processed": "false"}}
                logging.info("Scheduled row encountered errors.")

            update_result = scheduleRun.update_one({"_id": document_id}, document_update)
            logging.info(f"Updated document _id: {document_id}, Matched count: {update_result.matched_count}, Modified count: {update_result.modified_count}")

def main():
    logging.info("Started IFSS_RSA main routine")

    # Instrumentat setup here
    search_connect()
    logging.info("Connected to RSA306B")

    cf_mhz = 315.0
    span_mhz = 15.0
    rbw_khz = 15.0
    refLevel = -40
    
    # Convert MHz to Hz for the API calls
    cf_hz = cf_mhz * 1e6
    span_hz = span_mhz * 1e6
    rbw_hz = rbw_khz * 1e3
    
    specSet = config_spectrum(cf_hz, refLevel, span_hz, rbw_hz)
    spec_settings = Spectrum_Settings()
    err_check(rsa.SPECTRUM_GetSettings(byref(spec_settings)))
    trace_length = spec_settings.traceLength
    
    # Adjust frequency list calculation for 10 frequency points using MHz values
    startfreq_mhz = cf_mhz - (span_mhz / 2)
    stopfreq_mhz = cf_mhz + (span_mhz / 2)
    step_mhz = (stopfreq_mhz - startfreq_mhz) / (trace_length - 1)
    freq_list_mhz = [startfreq_mhz + i * step_mhz for i in range(trace_length)]

    try:
        process_schedule(specSet, freq_list_mhz)
        logging.info("Schedule finished for the day.\n")
    except Exception as e:
        logging.info(f"An error occurred in IFSS_PXA.py main(): {e}")
        restart_service()

if __name__ == "__main__":
    try:    
        main()
    except Exception as e:
        logging.error(f"An error occurred in IFSS_PXA.py: {e}")