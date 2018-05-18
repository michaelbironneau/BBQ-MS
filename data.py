import redis
import json
from iothub_client import *
import sys
import os
from apscheduler.schedulers.blocking import BlockingScheduler
import datetime
from threading import Lock
import math
import time
import json

lock = Lock()
THRESHOLD = 0.01  # COV threshold %

class eventhub_sender():
    def __init__(self, grill_sensor, meat_sensor, host_name, device_id, shared_key, protocol):
        self.redis = redis.StrictRedis(host='localhost', port=6379, db=0)
        self.device_id = device_id
        self.grill_sensor = grill_sensor
        self.meat_sensor = meat_sensor
        self.connection_string = 'HostName={0};DeviceId={1};SharedAccessKey={2}'.format(host_name, device_id, shared_key)
        if protocol.lower() == 'amqp':
            self.protocol = IoTHubTransportProvider.AMQP
        elif protocol.lower() == 'mqtt':
            self.protocol = IoTHubTransportProvider.MQTT
        else:
            self.protocol = IoTHubTransportProvider.HTTP
        self.connect()

    def connect(self):
        # Connect/reconnect to the IoT Hub
        self.iot_hub = IoTHubClient(self.connection_string, self.protocol)
        self.iot_hub.set_option('messageTimeout', 10000)
        self.last_ok = datetime.datetime.utcnow()

    def get_message(self):
        # Retrieve readings from Redis
        try:
            data = self.redis.rpoplpush('readings', 'readings-sending')
            return data
        except redis.RedisError as e:
            print('Unable to access Redis: {0}'.format(repr(e)))
            return None

    def get_reading(self, sensor, sensor_name):
        try:
             t = float(sensor.readTempC())
             if math.isnan(t):
                return None
             return json.dumps({'timestamp': int(time.time() * 1000), # Millis since epoch
                       'topic': 'readings',
                       'entity': self.device_id,
                       'created_at': datetime.datetime.utcnow().isoformat(),
                       'type': '{0}-temperature'.format(sensor_name),
                       'value': t})         
        except Exception as e:
            print('Failed to get message due to exception {0}'.format(e))

    def retry_failed(self):
        # Move anything on the processing list back to the main list in Redis
        lock.acquire()
        while True:
            failed = self.redis.rpoplpush('readings-sending', 'readings')
            if not failed:
                break
        lock.release()

    def msg_confirmation(self, message, result, user_context):
        print('Confirmation[%d] received for message with result = %s' % (user_context, result))
        if result == IoTHubClientConfirmationResult.OK:
            # Remove the message from Redis now that it is confirmed
            self.redis.lrem('readings-sending', 0, message.get_string())
            self.last_ok = datetime.datetime.utcnow()

    def read(self):
        reading_meat = self.get_reading(self.meat_sensor, "meat")
        if reading_meat:
            self.redis.lpush('readings', json.dumps(payload))
        reading_grill = self.get_reading(self.grill_sensor, "grill")
        if reading_grill:
            self.redis.lpush('readings', json.dumps(payload))
        
    def send(self):
        # Check if last good transmission is over 120s ago, try to reconnect if so
        if (datetime.datetime.utcnow() - self.last_ok).total_seconds() > 120:
            self.connect()

        lock.acquire()
        while True:
            # Take an item from the redis list
            data = self.get_message()
            if not data:
                lock.release()
                return None
            # Send message to event hub
            print('Sending: ', data)
            try:
                msg = IoTHubMessage(data)
                self.iot_hub.send_event_async(msg, self.msg_confirmation, 0)
            except IoTHubError as e:
                print('Error sending data to Azure EventHub: {0}'.format(repr(e)))

