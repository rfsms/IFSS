from ctypes import *
from time import sleep
from RSA_API import *
import sys
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
spectrumData = db["spectrumData"]
satSchedule = db["satSchedule"]

RTLD_LAZY = 0x0001
LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
rsa = CDLL("./libRSA_API.so", LAZYLOAD)
usbapi = CDLL("./libcyusb_shared.so", LAZYLOAD)

################ SETUP ################
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
        print('No instruments found. Exiting script.')
        sys.exit(0)
    elif numFound.value == 1:
        err_check(rsa.DEVICE_Connect(deviceIDs[0]))
    rsa.CONFIG_Preset()


################ DEFAULT CONFIG SETUP ################
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

def spectrum_capture():
    print("Connecting to the RSA306B...")
    search_connect()

    # Define center frequency, span, and RBW in MHz cause math...
    # cf_mhz = 1702.5
    # span_mhz = 15.0
    # rbw_khz = 15.0
    # refLevel = -80
    cf_mhz = 2437.0
    span_mhz = 20.0
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

    cycle = 0
    while cycle < 100: # Remove this later
        cycle += 1
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
        print(f'Last Trace Index: {cycle}')

    # def find_schedules_for_today():
    #     today_str = datetime.utcnow().strftime("%d-%b-%Y")
    #     print(f"Finding schedules for today (UTC): {today_str}")
    #     schedules = satSchedule.find({"startDate": today_str, "endDate": today_str})
    #     return list(schedules)

    # def spectrum_capture_for_schedule(start_time_str, end_time_str):
    #     now = datetime.now(timezone.utc)
    #     start_datetime = datetime.combine(now.date(), datetime.strptime(start_time_str, "%H:%M:%S").time(), tzinfo=timezone.utc)
    #     end_datetime = datetime.combine(now.date(), datetime.strptime(end_time_str, "%H:%M:%S").time(), tzinfo=timezone.utc)

    #     # Adjust for cases where end time is past midnight
    #     if end_datetime < start_datetime:
    #         end_datetime += timedelta(days=1)

    #     print(f"Starting capture for schedule from {start_time_str} to {end_time_str} (UTC).")
    #     while start_datetime <= now <= end_datetime:
    #         print('Capturing')
            
    #         trace = acquire_spectrum(specSet)
    #         currentTime = datetime.today().isoformat(sep=' ', timespec='milliseconds')

    #         frequencies = {str(round(freq, 4)): float(value) for freq, value in zip(freq_list_mhz, trace)}
    #         document = {
    #             "timestamp": currentTime,
    #             "frequencies": frequencies
    #         }
    #         spectrumData.insert_one(document)

    #         now = datetime.now(timezone.utc)
    #         sleep(1)

    # # Main loop to continuously check and process schedules
    # while True:
    #     schedules = find_schedules_for_today()
    #     if schedules:
    #         print(f"Found {len(schedules)} schedules for today (UTC).")
    #     else:
    #         print("No schedules found for today (UTC). Waiting for next schedule...")

    #     # Process each schedule found for today
    #     for schedule in schedules:
    #         print(schedule)
    #         start_time = schedule['startTime']
    #         end_time = schedule['endTime']
    #         print(f"Processing schedule (UTC): Start Time - {start_time}, End Time - {end_time}")
    #         spectrum_capture_for_schedule(start_time, end_time)

    #     # Wait until the start of the next day (UTC) to refresh the schedule
    #     now = datetime.now(timezone.utc)
    #     next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    #     wait_seconds = (next_day - now).total_seconds()
    #     print(f"Waiting for the next day's schedules. Sleeping for {wait_seconds} seconds...")
    #     sleep(wait_seconds)

def main():
    print("Starting continuous spectrum capture based on schedule...")
    spectrum_capture()

if __name__ == '__main__':
    main()
