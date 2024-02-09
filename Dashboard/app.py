from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import logging
import pymongo

# Logging setup
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename='/home/noaa_gms/IFSS/IFSS.log', level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

app = Flask(__name__)

socketio = SocketIO(app, async_mode='eventlet')

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["ifss"]
collection = db["spectrumData"]

# Custom log function for SocketIO
def log_socketio_error(event, error_info):
    logging.error(f"Error in SocketIO {event}: {error_info}")

@app.route('/')
def index():
    return render_template('index.html')

def fetch_latest_data():
    document = collection.find().sort([('_id', -1)]).limit(1)
    for doc in document:
        return doc['frequencies']

@app.route('/data')
def data():
    document = collection.find().sort([('_id', -1)]).limit(1)
    for doc in document:
        return jsonify(doc['frequencies'])
    return jsonify({})

@socketio.on('connect')
def handle_connect():
    try:
        logging.info("Client connected")
    except Exception as e:
        log_socketio_error('connect', str(e))

@socketio.on('request_data')
def handle_request_data():
    data = fetch_latest_data()
    socketio.emit('update_data', data)

@socketio.on('disconnect')
def handle_disconnect():
    try:
        logging.info("Client disconnected")
    except Exception as e:
        log_socketio_error('disconnect', str(e))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)