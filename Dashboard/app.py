from flask import Flask, render_template, jsonify
import logging
from pymongo import MongoClient
from datetime import datetime, timedelta

# Logging setup
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

app = Flask(__name__)

client = MongoClient("mongodb://localhost:27017/")
db = client["ifss"]
spectrumCollection = db["spectrumData"]
scheduleCollection = db["satSchedule"]

@app.route('/daily-schedule')
def daily_schedule():
    utc_now = datetime.utcnow()
    today_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    schedules_today = scheduleCollection.find({
        "timestamp": {
            "$gte": today_start,
            "$lt": today_end
        }
    })

    schedules_list = []
    for schedule in schedules_today:
        schedule["_id"] = str(schedule["_id"])
        schedules_list.append({
            "item": schedule.get("item"),
            "dir": schedule.get("dir"),
            "el": schedule.get("el"),
            "endDate": schedule.get("endDate"),
            "endTime": schedule.get("endTime"),
            "idle": schedule.get("idle"),
            "mode": schedule.get("mode"),
            "ovr": schedule.get("ovr"),
            "sat": schedule.get("sat"),
            "startDate": schedule.get("startDate"),
            "startTime": schedule.get("startTime"),
        })

    return jsonify(schedules_list)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    document = spectrumCollection.find().sort([('_id', -1)]).limit(1)
    for doc in document:
        return jsonify(doc['frequencies'])
    return jsonify({})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)