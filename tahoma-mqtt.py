#!/usr/bin/python3

import paho.mqtt.client as mqtt
import logging
import signal
import time
import json
import datetime
import requests
from pprint import pprint
from slugify import slugify
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

retry_strategy = Retry(
    total=5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)

adapter = HTTPAdapter(max_retries=retry_strategy)

FORMAT = ('%(asctime)-15s %(threadName)-15s '
          '%(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s')
logging.basicConfig(format=FORMAT)
log = logging.getLogger()
log.setLevel(logging.INFO)

mqtt_host="127.0.0.1"
mqtt_port=1883

kill_me_now=False

tahoma_topic = ''
tahoma_user = ''
tahoma_pass = ''
tahoma_session = None
tahoma_address = 'https://tahomalink.com'
tahoma_listener = None

def tahoma_connect():
    global tahoma_user, tahoma_pass, tahoma_session, tahoma_address
    global adapter
    tahoma_session = requests.Session()
    tahoma_session.mount("https://", adapter)
    tahoma_session.mount("http://", adapter)
    r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/login', [('userId', tahoma_user), ('userPassword', tahoma_pass)])
    response = r.json()
    return response['success']

def tahoma_devicelist():
    global tahoma_session, tahoma_address
    try:
        r = tahoma_session.get(tahoma_address + '/enduser-mobile-web/enduserAPI/setup/devices')
        # TODO add response validation
    except:
        #reconnect
        tahoma_connect()
        #retry
        r = tahoma_session.get(tahoma_address + '/enduser-mobile-web/enduserAPI/setup/devices')
    return r.json()

def tahoma_events():
    global tahoma_session, tahoma_address, tahoma_listener
    try:
        r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/events/' + tahoma_listener + '/fetch')
        # TODO add response validation, reconnect, retry
    except:
        tahoma_connect()
        r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/events/' + tahoma_listener + '/fetch')

    return r.json()

def tahoma_register_listener():
    global tahoma_session, tahoma_address, tahoma_listener
    r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/events/register')
    # TODO add response validation, reconnect, retry
    response = r.json()
    tahoma_listener = response['id']

def prepare_command(device, commands):
    commands_serialized = []
    commands_serialized.append(commands)
    actions_serialized = []
    action = {}
    
    action["deviceURL"] = device['deviceURL']
    action["commands"] = commands_serialized
    
    actions_serialized.append(action)
    data = {"label": device['label'] + ' - ' + commands["name"], "actions": actions_serialized}
    # self.json_data = json.dumps(data, indent=None, sort_keys=True)
    return data

def tahoma_exec(data):
    global tahoma_session, tahoma_address
    try:
        r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/exec/apply', json=data)
        # TODO add response validation, reconnect, retry
    except:
        tahoma_connect()
        r = tahoma_session.post(tahoma_address + '/enduser-mobile-web/enduserAPI/exec/apply', json=data)
    return r.json()

def exit_gracefully(signum, frame):
    global kill_me_now
    kill_me_now = True

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

mqtt.Client.bad_connection_flag=False
mqtt.Client.connected_flag=False
mqtt.Client.disconnect_flag=False
mqtt.Client.disconnect_time=0.0
mqtt.Client.pub_msg_count=0

mqttclient = mqtt.Client("tahoma-mqtt-client")

devices = []

def on_connect(client, userdata, flags, rc):
    if rc==0:
        client.connected_flag=True #set flag
        print("connected OK")
        client.subscribe("tahoma/#", 2)
    else:
        print("Bad connection Returned code=",rc)
        client.bad_connection_flag=True

def on_disconnect(client, userdata, rc):
    logging.info("disconnecting reason  "  +str(rc))
    client.connected_flag=False
    client.disconnect_flag=True

def on_publish(client, userdata, result):
    print("data published \n")
    pass

def on_log(client, userdata, level, buf):
    print("log: ",buf)

def on_message(client, userdata, message):
    global devices
    global tahoma_session, tahoma_user, tahoma_pass, tahoma_topic
    payload = ""
    commands = ""
    now = datetime.datetime.now()
    nowstr = now.strftime("%Y-%m-%d %H:%M:%S") + " - "
    if message != None:
        payload = str(message.payload.decode("utf-8"))
        commands = json.loads(payload)

    if message.topic == "tahoma/devices/list":
        tahoma_user = commands['user']
        tahoma_pass = commands['pass']
        tahoma_topic = commands['topic']
        if not tahoma_session:
            if not tahoma_connect():
                # unable to connect
                return
            else:
                tahoma_register_listener()
        
        devices = tahoma_devicelist()

        print(nowstr + "collecting devices")
        print(nowstr + "detected devices")
        # pprint(devices)
        client.publish("tahoma/" + tahoma_topic + "/devices", json.dumps(devices), qos=0, retain=True)
    
    for device in devices:

        if message.topic == "tahoma/" + tahoma_topic + "/" + slugify(device['deviceURL']) + "/set":
            # handle commands received from mqtt
            print("Received command for " + device['deviceURL'])
            pprint(commands)
            pprint(device)
            tahoma_exec(prepare_command(device, commands))
            continue
        
        # different topic for tilt device
        if message.topic == "tahoma/" + tahoma_topic + "/" + slugify(device['deviceURL'] + "_Tilt") + "/set":
            # handle commands received from mqtt
            print("Received command for " + device['deviceURL'] + "_Tilt")
            pprint(commands)
            tahoma_exec(prepare_command(device, commands))
            continue

mqttclient.on_connect = on_connect
mqttclient.on_disconnect = on_disconnect
mqttclient.on_publish = on_publish
mqttclient.on_log = on_log
mqttclient.on_message = on_message

mqttclient.loop_start()

try:
    mqttclient.connect(mqtt_host, mqtt_port) #connect to broker
    while not mqttclient.connected_flag: #wait in loop
        print("Waiting for connection")
        time.sleep(1)
except:
    print("connection failed")
    exit(1) #Should quit or raise flag to quit or retry

#mqttclient.subscribe("ngbs/#", qos=0)

while True and not mqttclient.bad_connection_flag and not kill_me_now:
    # poll device status
    if (not tahoma_session) and tahoma_user and tahoma_pass:
        tahoma_connect()
            
    if tahoma_session and tahoma_listener:
        events = tahoma_events()
        #filtered_events = list()
        for event in events:
            if event['name'] == 'DeviceStateChangedEvent':
                pprint(json.dumps(event['deviceStates']))
                if any(s['name'] == "core:SlateOrientationState" for s in event['deviceStates']):
                    # it a tilt so publish it to tilt device 
                    mqttclient.publish("tahoma/" + tahoma_topic + "/" + slugify(event['deviceURL'] + "_Tilt") + "/status" , json.dumps(event['deviceStates']), qos=0, retain=True)
                else:
                    mqttclient.publish("tahoma/" + tahoma_topic + "/" + slugify(event['deviceURL']) + "/status" , json.dumps(event['deviceStates']), qos=0, retain=True)


    time.sleep(5)

print("Stopping loop")
mqttclient.loop_stop()
print("disconnecting")
mqttclient.disconnect()
