import requests
from pymongo import MongoClient
from datetime import datetime
import re

def fetch_schedule():
    url = "http://soest-hcc1.hcc.hawaii.edu/scheduled_received/schedule.txt"
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
                if start_date == today:  # Check if the start date matches today's date
                    record = {
                        "item": parts[0],
                        "sat": parts[1].strip(),
                        "dir": parts[2],
                        "el": int(parts[3]),
                        "mode": parts[4],
                        "start": parts[5] + " " + parts[6],
                        "end": parts[7] + " " + parts[8],
                        "ovr": int(parts[9]),
                        "idle": int(parts[10]),
                        "timestamp": datetime.now()
                    }
                    data.append(record)
    return data

def insert_into_mongodb(data, collection):
    if data:  # Ensure there's data to insert
        for record in data:
            # Use the "item" field to identify the document for upsert operation
            query = {"item": record["item"]}
            update = {"$set": record}
            collection.update_one(query, update, upsert=True)

if __name__ == "__main__":
    client = MongoClient("mongodb://localhost:27017/")
    db = client["ifss"]
    collection = db["satSchedule"]
    
    # Ensure the unique index is created on the collection
    create_unique_index(collection)
    
    schedule_text = fetch_schedule()
    schedule_data = parse_schedule(schedule_text)
    
    # Proceed if there's parsed data and insert it into MongoDB
    insert_into_mongodb(schedule_data, collection)
