import requests
from pymongo import MongoClient
from datetime import datetime
import re

'''
Designed to fetch satellite schedule data from a selected earth station EOS-FES, 
parse the data to filter records for the current day since the schedule is a 48 hour window, 
and then insert the records into a MongoDB db ('ifss') collection ('satSchedule').

Sample Data vs regex (parts[])
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

client = MongoClient("mongodb://localhost:27017/")
db = client["ifss"]
collection = db["satSchedule"]

def fetch_schedule():
    url = "https://dbps.aoml.noaa.gov/scheduled_received/schedule.txt"
    # url = "http://soest-hcc1.hcc.hawaii.edu/scheduled_received/schedule.txt"
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def create_unique_index(collection):
    # Use ITEM as the primary key
    collection.create_index([("item", 1)], unique=True)

def parse_schedule(text):
    today = datetime.now().strftime("%d-%b-%Y")
    lines = text.strip().split("\n")
    data = []
    for line in lines:
        if line and not line.startswith("-") and not line.startswith("ITEM") and line[0].isdigit():
            match = re.match(r"(\d+)\s+([\w\s-]+)\s+(\w)\s+(\d+)\s+(\w+)\s+(\d+-\w+-\d+)\s+(\d+:\d+:\d+)\s+(\d+-\w+-\d+)\s+(\d+:\d+:\d+)\s+(\d+)\s+(\d+)", line)
            if match:
                parts = match.groups()
                start_date = parts[5]
                if start_date == today:
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
                        "idle": int(parts[10]),
                        "timestamp": datetime.now()
                    }
                    data.append(record)
    return data

def insert_into_mongodb(data, collection):
    if data:
        for record in data:
            query = {"item": record["item"]}
            update = {"$set": record}
            collection.update_one(query, update, upsert=True)

if __name__ == "__main__":
    create_unique_index(collection)
    
    schedule_text = fetch_schedule()
    schedule_data = parse_schedule(schedule_text)
    
    insert_into_mongodb(schedule_data, collection)
