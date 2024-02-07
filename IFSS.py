from ctypes import *
from time import sleep
import numpy as np
from RSA_API import *
import sys
from datetime import datetime

RTLD_LAZY = 0x0001
LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
rsa = CDLL("./libRSA_API.so",LAZYLOAD)
usbapi = CDLL("./libcyusb_shared.so",LAZYLOAD)

"""################CLASSES AND FUNCTIONS################"""
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
    print('API Version {}'.format(apiVersion.value.decode()))
    #

    err_check(rsa.DEVICE_Search(byref(numFound), deviceIDs,
                                deviceSerial, deviceType))

    if numFound.value < 1:
        print('No instruments found. Exiting script.')
        sys.exit(0)
    elif numFound.value == 1:
        # print('One device found.')
        # print('Device type: {}'.format(deviceType.value.decode()))
        # print('Device serial number: {}'.format(deviceSerial.value.decode()))
        print(f'Device Found: {deviceType}- {deviceSerial}')
        err_check(rsa.DEVICE_Connect(deviceIDs[0]))
    rsa.CONFIG_Preset()

def get_all_spectrum_settings():
    spec_settings = Spectrum_Settings()
    err_check(rsa.SPECTRUM_GetSettings(byref(spec_settings)))

    # Access the traceLength from the settings
    trace_length = spec_settings.traceLength

    print(f"Trace Length: {trace_length}")
    # Extract and print the settings
    span = spec_settings.span
    rbw = spec_settings.rbw
    enableVBW = spec_settings.enableVBW
    vbw = spec_settings.vbw
    trace_length = spec_settings.traceLength
    window = spec_settings.window
    vertical_unit = spec_settings.verticalUnit
    actual_start_freq = spec_settings.actualStartFreq
    actual_stop_freq = spec_settings.actualStopFreq
    actual_freq_step_size = spec_settings.actualFreqStepSize
    actual_rbw = spec_settings.actualRBW
    actual_vbw = spec_settings.actualVBW
    actual_num_iq_samples = spec_settings.actualNumIQSamples

    print(f"Span: {span / 1e6} MHz")
    print(f"RBW: {rbw / 1e3} kHz")
    print(f"Enable VBW: {enableVBW}")
    print(f"VBW: {vbw / 1e3} kHz")
    print(f"Trace Length: {trace_length}")
    print(f"Window: {window}")
    print(f"Vertical Unit: {vertical_unit}")
    print(f"Actual Start Frequency: {actual_start_freq / 1e6} MHz")
    print(f"Actual Stop Frequency: {actual_stop_freq / 1e6} MHz")
    print(f"Actual Frequency Step Size: {actual_freq_step_size / 1e3} kHz")
    print(f"Actual RBW: {actual_rbw / 1e3} kHz")
    print(f"Actual VBW: {actual_vbw / 1e3} kHz")
    print(f"Actual Number of IQ Samples: {actual_num_iq_samples}")

"""################SPECTRUM EXAMPLE################"""
def config_spectrum(cf=1e9, refLevel=0, span=40e6, rbw=300e3):
    rsa.SPECTRUM_SetEnable(c_bool(True))
    rsa.CONFIG_SetCenterFreq(c_double(cf))
    rsa.CONFIG_SetReferenceLevel(c_double(refLevel))

    rsa.SPECTRUM_SetDefault()
    specSet = Spectrum_Settings()
    rsa.SPECTRUM_GetSettings(byref(specSet))
    specSet.window = SpectrumWindows.SpectrumWindow_Kaiser
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
    rsa.SPECTRUM_GetTrace(traceSelector, specSet.traceLength, byref(traceData),
                          byref(outTracePoints))
    rsa.DEVICE_Stop()
    return np.array(traceData)

def spectrum_csv_capture():
    print('\n\n########Continuous Trace Saver########')
    search_connect()

    get_all_spectrum_settings()
    
    # Define center frequency, span, and RBW in MHz for readability
    cf_mhz = 2020
    span_mhz = 10.0
    rbw_khz = 10.0
    refLevel = 30
    
    # Convert MHz to Hz for the API calls
    cf_hz = cf_mhz * 1e6
    span_hz = span_mhz * 1e6
    print(f'span_hz: {span_hz}')
    rbw_hz = rbw_khz * 1e3
    
    specSet = config_spectrum(cf_hz, refLevel, span_hz, rbw_hz)
    print(f'specSet: {specSet}')
    filetime = datetime.today().strftime('%Y%m%d-%H%M%S')
    filename = f'/home/noaa_gms/IFSS/traces{filetime}.csv'
    
    # Adjust frequency list calculation for 10 frequency points using MHz values
    total_points = 10
    startfreq_mhz = cf_mhz - (span_mhz / 2)
    # print(f'Start: {startfreq_mhz}')
    stopfreq_mhz = cf_mhz + (span_mhz / 2)
    # print(f'Stop: {stopfreq_mhz}')
    freq_list_mhz = np.linspace(startfreq_mhz, stopfreq_mhz, total_points)
    
    # Round each frequency value to four decimal places and convert to string
    header = 'Timestamp,' + ','.join(map(lambda f: f"{round(f, 4)}", freq_list_mhz))
    # print(f'Header: {header}')
    
    a = 0
    while a < 2:  # Simplified loop condition for demonstration
        a += 1
        trace = acquire_spectrum(specSet)
        # print(f'Trace: {trace}')
        
        # Sample the trace to reduce to 10 points
        sampled_trace = np.linspace(trace[0], trace[-1], total_points)
        # print(f'Sampled Trace: {sampled_trace}')
        
        currenttime = datetime.today().isoformat(sep=' ', timespec='milliseconds')
        # data_row = currenttime + ',' + ','.join(map(str, sampled_trace))
        data_row = currenttime + ',' + ','.join(map(lambda x: f"{round(x, 4)}", sampled_trace))
        # print(f'Data Row: {data_row}')

        mode = 'w' if a == 1 else 'a'  # Overwrite if first iteration, append otherwise
        with open(filename, mode) as f:
            if a == 1:
                f.write(header + '\n')  # Write header only on first iteration
            f.write(data_row + '\n')
        
        sleep(1)
        print(f'\rCurrent Trace Index: {a}\n', end='')
        
        if a % 2 == 0:
            print("   Saving...")

def main():
    spectrum_csv_capture()

if __name__ == '__main__':
    main()
