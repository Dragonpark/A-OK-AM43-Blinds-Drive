#!/usr/bin/env python3

#curl -i http://localhost:5000/am43/<action>               --> Send action to all devices in ini file
#curl -i http://localhost:5000/am43/<action>/dev/<Device>  --> Send action to a specific device
#curl -i http://localhost:5000/am43/<action>/grp/<Group>   --> Send action to all devices in a device group

#<Action> options:
# <number 0-100>    --> Set blinds to position wanted
# open              --> Opening blinds
# close             --> Closing blinds
# getStatus         --> Get battery status, current position and light in %

from bluepy import btle
import configparser
import os
from flask import Flask
import datetime
from retrying import retry
import json


#Variables
config = configparser.ConfigParser() #Read ini file for meters
inifilepath = "/A-OK_AM43_Blind_Drive/AOK-AM43.ini"
app = Flask(__name__)

# AM43 Notification Identifiers
# Msg format: 9a <id> <len> <data * len> <xor csum>
IdMove = 0x0d  #not used in code yet
IdStop = 0x0a
IdBattery = 0xa2
IdLight = 0xaa
IdPosition = 0xa7
IdPosition2 = 0xa8  #not used in code yet
IdPosition3 = 0xa9  #not used in code yet
ACTIONS = ['open',
           'close',
           'stop',
           'getStatus']
BatteryPct = None
LightPct = None
PositionPct = None

#Check and read inifile
if (os.path.exists(inifilepath)):
    config.read(inifilepath)
else:
    print()
    print("ERROR: Cannot find ini file: " + inifilepath + "! Correct the path in this script or put the ini file in the correct directory. Exiting", flush=True)
    print()
    exit(1)

class AM43Delegate(btle.DefaultDelegate):
    def __init__(self):
        btle.DefaultDelegate.__init__(self)
    def handleNotification(self, cHandle, data):
        if (data[1] == IdBattery):
            global BatteryPct
            #print("Battery: " + str(data[7]) + "%")
            BatteryPct = data[7]
        elif (data[1] == IdPosition):
            global PositionPct
            #print("Position: " + str(data[5]) + "%")
            PositionPct = data[5]
        elif (data[1] == IdLight):
            global LightPct
            #print("Light: " + str(data[4] * 12.5) + "%")
            LightPct = data[4] * 12.5
        else:
            print("Unknown identifier notification recieved: " + str(data[1:2]))

# Constructs message and write to blind controller
def write_message(characteristic, dev, id, data, bWaitForNotifications):
    ret = False

    # Construct message
    msg = bytearray({0x9a})
    msg += bytearray({id})
    msg += bytearray({len(data)})
    msg += bytearray(data)

    # Calculate checksum (xor)
    csum = 0
    for x in msg:
        csum = csum ^ x
    msg += bytearray({csum})
    
    #print("".join("{:02x} ".format(x) for x in msg))
    
    if (characteristic):
        result = characteristic.write(msg)
        if (result["rsp"][0] == "wr"):
            ret = True
            if (bWaitForNotifications):
                if (dev.waitForNotifications(10)):
                    #print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " -->  BTLE Notification recieved", flush=True)
                    pass
    return ret


@retry(stop_max_attempt_number=2,wait_fixed=2000)
def ScanForBTLEDevices():
    scanner = btle.Scanner()
    print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Scanning for bluetooth devices....", flush=True)
    devices = scanner.scan()

    bAllDevicesFound = True
    for blind in config['AM43_BLE_Devices']:
        blindMAC = config.get('AM43_BLE_Devices', blind)  # Read BLE MAC from ini file
        
        bFound = False
        for dev in devices:
            if (blindMAC == dev.addr):
                print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Found " + blindMAC, flush=True)
                bFound = True
                break
            #else: 
                #bFound = False
        if bFound == False:
            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " " + blindMAC + " not found on BTLE network!", flush=True)
            bAllDevicesFound = False
        
    if (bAllDevicesFound == True):
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Every AM43 Blinds Controller is found on BTLE network", flush=True)
        return
    else:
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Not all AM43 Blinds Controllers are found on BTLE network, restarting bluetooth stack and checking again....", flush=True)
        os.system("service bluetooth restart")
        raise ValueError(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Not all AM43 Blinds Controllers are found on BTLE network, restarting bluetooth stack and check again....")


@retry(stop_max_attempt_number=10,wait_fixed=2000)
def connectBLE(blindMAC,blind):        
    try:
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Connecting to " + blindMAC + ", " + blind.capitalize() + "...", flush=True)
        dev = btle.Peripheral(blindMAC)
        return dev
    except:
        raise ValueError(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Cannot connect to " + blindMAC + " trying again....")

        
@app.route("/")
def hello():
    return "A-OK AM43 BLE Smart Blinds Drive Service\n\n"

def prnt_message(message):
    print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " --> " + message, flush=True)

@app.route("/am43/<action>",methods=['GET','PUT'])               ##curl -i http://localhost:5000/am43/<action>        Send specified action to all devices
@app.route("/am43/<action>/device/<dev>",methods=['GET','PUT'])  ##curl -i http://localhost:5000/am43/<action>/<dev>  Send specified action to an individual device
@app.route("/am43/<action>/group/<grp>",methods=['GET','PUT'])   ##curl -i http://localhost:5000/am43/<action>/<grp>  Send specified action to all devices in a group
def am43action(action,grp=None,dev=None):
    #Variables#
    ResultDict = {}
    
    ## Setup ##
    # Verify specified action is supported or is digit between 0 and 100
    if (action in ACTIONS) or (action.isdigit() and 0 <= int(action) <= 100):
        prnt_message(f"Unknown Blindsaction command: {action}")
        bSuccess = False
        return
    # Verify proper method was used
    if (request.method == 'PUT' and action == 'getStatus') or
       (request.method == 'GET' and action != 'getStatus'):
        prnt_message(f"Method { request.method } incorrect for action { action }")
        bSuccess = False
        return
    # Identify groups
    if grp:
        # Check if the specified section exists in the config file
        if config.has_section(grp):
            grps = [grp]
        else:
            ### REPLACE WITH FILEPATH USED
            prnt_message(f"Config section { grp } not valid. Please recheck config file")
            return
    elif not dev:
        grps = config.sections()
    # Retrieve list of devices based on specified group
    devs = []
    if grps:
        for g in grps:
            devs += config.items(g)
    if dev:
        for g in grps:
            for d in config.items(g):
                if dev in d[1]:
                    devs += [dev]
                    return
    
    if len(devs):
        ### 
    # Scan for BTLE devices
    try:
        #ScanForBTLEDevices()
        pass
    except:
        prnt_message(f" ERROR SCANNING FOR ALL BTLE Devices, trying to {action} the blinds anyway....")
        prnt_message(f" Please check any open connections to the blinds motor and close them, the Blinds Engine App perhaps?")
        pass
        #return "ERROR SCANNING FOR ALL BTLE Devices\n"

    # Loop through groups and devices
    for dev in devs:
        # Reset variables
        bSuccess = False

        try:
            dev = connectBLE(blindMAC,blind)
        except:
            prnt_message(f" ERROR, Cannot connect to {blindMAC}")
            prnt_message(f" Please check any open connections to the blinds motor and close them, the Blinds Engine App perhaps?")
            continue

        prnt_message(f" --> Connected to {dev.addr} {blind.capitalize()}")

        blindsvc = dev.getServiceByUUID("fe50")
        if (blindsvc):
            blindsvcChars = blindsvc.getCharacteristics("fe51")[0]
            if (blindsvcChars):
                if action != 'getStatus':
                    switch (action):
                        case 'open':  data = [0]
                        case 'close': data = [100]
                        case 'stop':  data = [0xcc]
                        default:      data = [int(action)]

                    bSuccess = write_message(blindsvcChars, dev, IdMove, data, False)
                     
                    if (bSuccess):
                        prnt_message(f" ----> Writing {action} to {blind.capitalize()} was succesfull!")
                    else:
                        prnt_message(f" ----> Writing to {blind.capitalize()} FAILED")

                    ResultDict.update({blind.capitalize(): [{"command":action, "bSuccess":bSuccess, "macaddr":blind}]})

                else:
                    if blindsvcChars.supportsRead():
                        bSuccess = dev.setDelegate(AM43Delegate())
                        bSuccess = write_message(blindsvcChars, dev, IdBattery, [0x01], True)
                        bSuccess = write_message(blindsvcChars, dev, IdLight, [0x01], True)
                        bSuccess = write_message(blindsvcChars, dev, IdPosition, [0x01], True)

                        #retrieve global variables with current percentages
                        global BatteryPct 
                        global LightPct
                        global PositionPct
                        prnt_message(f" ----> Battery level: {str(BatteryPct)}%, " +
                            "Blinds position: {str(PositionPct)}%, " +
                            "Light sensor level: {str(LightPct)}%")
                        ResultDict.update({blind.capitalize(): [{"battery":BatteryPct, "position":PositionPct, "light":LightPct, "macaddr":blindMAC}]})

                        # Reset variables
                        BatteryPct = None
                        LightPct = None
                        PositionPct = None

                    else:
                        prnt_message(f" ----> No reads allowed on characteristic!")

                else:
                    prnt_message(f" --> Unknown Blindsaction command: {action}")
                    bSuccess = False
                    #result = None

            # Close connection to BLE device
            dev.disconnect()

    if (bSuccess):
        ResultDict.update({"status":"OK"})
    else:
        ResultDict.update({"status":"ERROR"})
    #return json.dumps(ResultDict) + "\n"  #Oneliner result if you would like
    return json.dumps(ResultDict, indent=4, sort_keys=True) + "\n"
    
if __name__ == "__main__":
    os.system('clear')  # Clear screen
    app.run(host='0.0.0.0') #Listen to all interfaces  #,debug=True

