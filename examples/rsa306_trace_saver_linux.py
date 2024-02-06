"""
Tektronix RSA_API Example
Author: Morgan Allison
Date created: 6/15
Date edited: 9/17
Windows 7 64-bit
RSA API version 3.11.0047
Python 3.6.1 64-bit (Anaconda 4.4.0)
NumPy 1.13.1, MatPlotLib 2.0.2
Download Anaconda: http://continuum.io/downloads
Anaconda includes NumPy and MatPlotLib
Download the RSA_API: http://www.tek.com/model/rsa306-software
Download the RSA_API Documentation:
http://www.tek.com/spectrum-analyzer/rsa306-manual-6

YOU WILL NEED TO REFERENCE THE API DOCUMENTATION
"""

from ctypes import *
from os import chdir
from time import sleep
import numpy as np
import matplotlib.pyplot as plt
from RSA_API import *
import sys
import numpy
from datetime import datetime

from matplotlib import __version__ as __mversion__
print('Matplotlib Version:', __mversion__)
print('Numpy Version:', np.__version__)


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

    err_check(rsa.DEVICE_Search(byref(numFound), deviceIDs,
                                deviceSerial, deviceType))

    if numFound.value < 1:
        # rsa.DEVICE_Reset(c_int(0))
        print('No instruments found. Exiting script.')
        sys.exit(0)
    elif numFound.value == 1:
        print('One device found.')
        print('Device type: {}'.format(deviceType.value.decode()))
        print('Device serial number: {}'.format(deviceSerial.value.decode()))
        err_check(rsa.DEVICE_Connect(deviceIDs[0]))
    else:
        # corner case
        print('2 or more instruments found. Enumerating instruments, please wait.')
        for inst in deviceIDs:
            rsa.DEVICE_Connect(inst)
            rsa.DEVICE_GetSerialNumber(deviceSerial)
            rsa.DEVICE_GetNomenclature(deviceType)
            print('Device {}'.format(inst))
            print('Device Type: {}'.format(deviceType.value))
            print('Device serial number: {}'.format(deviceSerial.value))
            rsa.DEVICE_Disconnect()
        # note: the API can only currently access one at a time
        selection = 1024
        while (selection > numFound.value - 1) or (selection < 0):
            selection = int(raw_input('Select device between 0 and {}\n> '.format(numFound.value - 1)))
        err_check(rsa.DEVICE_Connect(deviceIDs[selection]))
    rsa.CONFIG_Preset()


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


def create_frequency_array(specSet):
    # Create array of frequency data for plotting the spectrum.
    freq = np.arange(specSet.actualStartFreq, specSet.actualStartFreq
                     + specSet.actualFreqStepSize * specSet.traceLength,
                     specSet.actualFreqStepSize)
    return freq


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
    cf = 1.7025e9
    refLevel = 0
    span = 15e6
    rbw = 10e3
    specSet = config_spectrum(cf, refLevel, span, rbw)
    
    print("306 Config:")
    print("CF= ",cf)
    print("Ref. Lvl.= ",refLevel)
    print("Span=",span)
    print("RBW= ",rbw)
    
    filetime=datetime.today().strftime('%Y.%m.%d-%H.%M.%S')
    filename='/home/noaa_gms/rsatraces/306trace'+filetime+'.csv'
    
    startfreq=cf-(span/2)
    stopfreq=cf+(span/2)
    step=(span/801)
    freq_list=np.arange(startfreq,stopfreq,step)
    freq_list=np.hstack(('Timestamp',freq_list))
    
    trace_array=freq_list
    

    a=0
    while True:
        a=a+1
        trace=acquire_spectrum(specSet)
        currenttime=datetime.today().isoformat(sep=' ',timespec='milliseconds')
        trace=np.hstack((currenttime,trace))
        trace_array=np.vstack((trace_array,trace))
        sleep(1)
        b='Current Trace Index: '+str(a)
        sys.stdout.write('\r'+b)
        if a%10==0:
            f=open(filename,'a')
            numpy.savetxt(f, trace_array, delimiter=",",fmt='%s')
            print("   Saving...")
            f.close()
            
            #Grab a fresh trace before before starting loop again. 
            trace=acquire_spectrum(specSet)
            currenttime=datetime.today().isoformat(sep=' ',timespec='milliseconds')
            trace=np.hstack((currenttime,trace))
            trace_array=trace




def spectrum_example():
    print('\n\n########Spectrum Example########')
    search_connect()
    cf = 1.745e9
    refLevel = 0
    span = 20e6
    rbw = 10e3
    specSet = config_spectrum(cf, refLevel, span, rbw)
    

    trace = acquire_spectrum(specSet)
    
    
    f=open('C:/users/skylar/documents/ue_23dbm_75rb-6.8sa.csv','a')
    numpy.savetxt(f, numpy.column_stack(trace), delimiter=",")
    
    
    freq = create_frequency_array(specSet)
    peakPower, peakFreq = peak_power_detector(freq, trace)

    f.close()
    plt.figure(1, figsize=(15, 10))
    ax = plt.subplot(111, facecolor='k')
    ax.plot(freq, trace, color='y')
    ax.set_title('Spectrum Trace')
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Amplitude (dBm)')
    ax.axvline(peakFreq)
    ax.text((freq[0] + specSet.span / 20), peakPower,
            'Peak power in spectrum: {:.2f} dBm @ {} MHz'.format(
                peakPower, peakFreq / 1e6), color='white')
    ax.set_xlim([freq[0], freq[-1]])
    ax.set_ylim([refLevel - 100, refLevel])
    plt.tight_layout()
    plt.show()
    rsa.DEVICE_Disconnect()


"""################MISC################"""
def config_trigger(trigMode=TriggerMode.triggered, trigLevel=-10,
                   trigSource=TriggerSource.TriggerSourceIFPowerLevel):
    rsa.TRIG_SetTriggerMode(trigMode)
    rsa.TRIG_SetIFPowerTriggerLevel(c_double(trigLevel))
    rsa.TRIG_SetTriggerSource(trigSource)
    rsa.TRIG_SetTriggerPositionPercent(c_double(10))


def peak_power_detector(freq, trace):
    peakPower = np.amax(trace)
    peakFreq = freq[np.argmax(trace)]

    return peakPower, peakFreq


def main():
    # uncomment the example you'd like to run

    #spectrum_example()
    spectrum_csv_capture()
    # block_iq_example()
    #dpx_example()
    # if_stream_example()
    # iq_stream_example()

if __name__ == '__main__':
    main()
