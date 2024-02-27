from ctypes import *
from time import sleep
from RSA_API import *
import sys
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# try:
#     # Attempt to connect to MongoDB replica set
#     client = MongoClient('mongodb://127.0.0.1:27017/?replicaSet=rs0')
#     # Force a connection to verify our client can talk to the server
#     client.admin.command('ping')
#     print("MongoDB connection successful")
# except ConnectionFailure as e:
#     print(f"MongoDB connection failed: {e}")

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/?replicaSet=rs0')
db = client["ifss"]
spectrumData = db["spectrumData"]
satSchedule = db["satSchedule"]

# # Attempt to find the first document in the 'spectrumData' collection
# first_document = spectrumData.find_one()

# if first_document:
#     print("First document in 'spectrumData':", first_document)
# else:
#     print("No documents found in 'spectrumData'.")

RTLD_LAZY = 0x0001
LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
rsa = CDLL("/home/noaa_gms/IFSS/Tools/lib/libRSA_API.so", LAZYLOAD)
usbapi = CDLL("/home/noaa_gms/IFSS/Tools/lib/libcyusb_shared.so", LAZYLOAD)

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

def spectrum_capture(specSet, freq_list_mhz):

    cycle = 0
    while cycle < 20: # Remove this later
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

        sleep(.1) 
        print(f'Last Trace Index: {cycle}')

def main():
    search_connect()
    print("Connected to the RSA306B")

    # Define center frequency, span, and RBW in MHz cause math...
    # cf_mhz = 1702.5
    # span_mhz = 15.0
    # rbw_khz = 15.0
    # refLevel = -80
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

    print("Starting spectrum capture")
    spectrum_capture(specSet, freq_list_mhz)

if __name__ == '__main__':
    main()
