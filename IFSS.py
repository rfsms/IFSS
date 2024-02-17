import schedule
from time import sleep
from datetime import datetime
import logging
import json
from pymongo import MongoClient
import IFSS

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client["ifss"]
spectrumData = db["spectrumData"]
satSchedule = db["satSchedule"]

# Reset the Root Logger and seup logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS_SA.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Check if the current time is 00:00 UTC or later, and if so, call RFSS_{SPECAN}.main()
if datetime.datetime.utcnow().time() >= datetime.time(0, 0):
    logging.info('-----------------------------------------------------')
    logging.info('RFSS service restarted. Using current schedule.')
    IFSS.main()