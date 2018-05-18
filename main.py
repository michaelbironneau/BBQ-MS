#!/usr/bin/python
# Can enable debug output by uncommenting:
#import logging
#logging.basicConfig(level=logging.DEBUG)

import time
import math
import sys 
import json
from data import eventhub_sender
import Adafruit_GPIO.SPI as SPI
import Adafruit_GPIO.MAX31855 as MAX31855
from apscheduler.schedulers.blocking import BlockingScheduler
import os

# Raspberry Pi software SPI configuration.
CLK = 25
CS  = 24
DO  = 18
grill_sensor = MAX31855.MAX31855(CLK, CS, DO)

# Sensor 2
CLK_2 = 22
DO_2 = 17
CS_2 = 27
meat_sensor = MAX31855.MAX31855(CLK_2, CS_2, DO_2)

if __name__ == '__main__':
    # Load settings file
    settings_file = sys.argv[-1]
    with open(settings_file) as f:
        settings = json.load(f)

    # Set up scheduler
    scheduler = BlockingScheduler()
    # Class to send data
    sender = eventhub_sender(grill_sensor, meat_sensor,
                             os.getenv('IOT_HOST', settings.get('iot-host', 'oeiot.azure-devices.net')),
                             os.getenv('DEVICE_ID', settings.get('device-id', '')),
                             os.getenv('SHARED_KEY', settings.get('shared-key', '')),
                             os.getenv('PROTOCOL', settings.get('protocol', 'mqtt')))
    scheduler.add_job(sender.read,
                      'interval', seconds=settings.get('read-interval', 1),
                      id='read_data', coalesce=True)
    scheduler.add_job(sender.send,
                      'interval', seconds=settings.get('data-send-interval', 1),
                      id='send_data', coalesce=True)
    scheduler.add_job(sender.retry_failed, 'interval', seconds=120,
                      id='retry_failed', coalesce=True)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass