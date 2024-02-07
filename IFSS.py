from ctypes import *
from time import sleep
import numpy as np
from RSA_API import *
import sys
from datetime import datetime
import os

# RTLD_LAZY = 0x0001
# LAZYLOAD = RTLD_LAZY | RTLD_GLOBAL
# rsa = CDLL("./libRSA_API.so",LAZYLOAD)
# usbapi = CDLL("./libcyusb_shared.so",LAZYLOAD)

# C:\Tektronix\RSA_API\lib\x64 needs to be added to the
# PATH system environment variable
# os.chdir("C:\\Tektronix\\RSA_API\\lib\\x64")
rsa = cdll.LoadLibrary("C:\\Tektronix\\RSA_API\\lib\\x64\\RSA_API.dll")

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
    print('API Version {}\n'.format(apiVersion.value.decode()))
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
        err_check(rsa.DEVICE_Connect(deviceIDs[0]))
    rsa.CONFIG_Preset()

def get_all_spectrum_settings():
    try:
        spec_settings = Spectrum_Settings()
        err_check(rsa.SPECTRUM_GetSettings(byref(spec_settings)))

        # Extract and print the settings
        span = spec_settings.span
        rbw = spec_settings.rbw
        # enableVBW = spec_settings.enableVBW
        # vbw = spec_settings.vbw
        trace_length = spec_settings.traceLength
        # window = spec_settings.window
        # vertical_unit = spec_settings.verticalUnit
        actual_start_freq = spec_settings.actualStartFreq
        actual_stop_freq = spec_settings.actualStopFreq
        actual_freq_step_size = spec_settings.actualFreqStepSize
        actual_rbw = spec_settings.actualRBW
        actual_vbw = spec_settings.actualVBW
        # actual_num_iq_samples = spec_settings.actualNumIQSamples

        settings_summary = f"""
Span: {span / 1e6} MHz
RBW: {rbw / 1e3} kHz
Trace Length: {trace_length}
Actual Start Frequency: {actual_start_freq / 1e6} MHz
Actual Stop Frequency: {actual_stop_freq / 1e6} MHz
Actual Frequency Step Size: {actual_freq_step_size / 1e3} kHz
Actual RBW: {actual_rbw / 1e3} kHz
Actual VBW: {actual_vbw / 1e3} kHz
        """

        print(settings_summary)
        return "Settings retrieved successfully."
    
    except Exception as e:
            return f"Error retrieving settings: {str(e)}"

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
    
    # Define center frequency, span, and RBW in MHz for readability
    cf_mhz = 2020
    print(f'CF: {cf_mhz} MHz')
    span_mhz = 20.0
    rbw_khz = 15.0
    refLevel = -80
    
    # Convert MHz to Hz for the API calls
    cf_hz = cf_mhz * 1e6
    span_hz = span_mhz * 1e6
    rbw_hz = rbw_khz * 1e3
    
    specSet = config_spectrum(cf_hz, refLevel, span_hz, rbw_hz)
    filetime = datetime.today().strftime('%Y%m%d-%H%M%S')
    filename = f'C:\\Users\\novaj\\IFSS\\{filetime}.csv'
    spec_settings = Spectrum_Settings()
    err_check(rsa.SPECTRUM_GetSettings(byref(spec_settings)))
    trace_length = spec_settings.traceLength
    
    # Adjust frequency list calculation for 10 frequency points using MHz values
    total_points = trace_length
    startfreq_mhz = cf_mhz - (span_mhz / 2)
    stopfreq_mhz = cf_mhz + (span_mhz / 2)
    freq_list_mhz = np.linspace(startfreq_mhz, stopfreq_mhz, total_points)
    
    get_all_spectrum_settings()

    # Round each frequency value to four decimal places and convert to string
    header = 'Timestamp,' + ','.join(map(lambda f: f"{round(f, 4)}", freq_list_mhz))
    
    cycle = 0
    while cycle < 1: # Remove this later
        cycle += 1
        trace = acquire_spectrum(specSet)
             
        currentTime = datetime.today().isoformat(sep=' ', timespec='milliseconds')

        # Find the index of the highest peak in the trace
        peak_index = np.argmax(trace)
        # Find the power level of the highest peak
        highest_peak_power = trace[peak_index]
        # Find the frequency corresponding to the highest peak
        peak_frequency_mhz = freq_list_mhz[peak_index]

        mode = 'w' if cycle == 1 else 'a'
        with open(filename, mode) as f:
            if cycle == 1:
                f.write(header + '\n')
            trace_str = currentTime + ',' + ','.join(map(str, trace))
            f.write(trace_str + '\n')
        
        sleep(1) 
        print(f'\rCurrent Trace Index: {cycle} - Highest Peak: {highest_peak_power:.2f} dBm at {peak_frequency_mhz:.4f} MHz', end='')


def main():
    spectrum_csv_capture()

if __name__ == '__main__':
    main()
