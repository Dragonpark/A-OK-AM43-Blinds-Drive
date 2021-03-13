#!/usr/bin/env python3

# To install libraries needed:
# sudo pip3 install Flask, bluepy, retrying

# Version 1.1 - Bas Bahlmann - The Netherlands
# Added battery status, current position and amount of light through new CheckStatus command. Disabled the scanning function, seems to work reliable without it
# Return values are in JSON format so you can interpret it easily

# Version 1.2 - Bas Bahlmann - The Netherlands
# Added percentage for positioning blinds, optimalization on code
# Added support for multiple Rooms/DeviceGroups

#curl -i http://localhost:5000/am43/<Action>  --> For the default setup
#curl -i http://localhost:5000/am43/<Action>/<DeviceGroup>  --> For the devicegroup setup you can specify in the ini file

#<Action> options:
# <number 0-100>    --> Set blinds to position wanted
# Open              --> Opening blinds
# Close             --> Closing blinds
# getStatus       --> Get battery status, current position and light in %

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
def ConnectBTLEDevice(blindMAC,blind):        
    try:
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Connecting to " + blindMAC + ", " + blind.capitalize() + "...", flush=True)
        dev = btle.Peripheral(blindMAC)
        return dev
    except:
        raise ValueError(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Cannot connect to " + blindMAC + " trying again....")

        
@app.route("/")
def hello():
    return "A-OK AM43 BLE Smart Blinds Drive Service\n\n"

@app.route("/am43/<action>",methods=['GET','PUT'])       ##curl -i http://localhost:5000/am43/<action>        Send specified action to all devices
@app.route("/am43/<action>/<dev>",methods=['GET','PUT']) ##curl -i http://localhost:5000/am43/<action>/<dev>  Send specified action to an individual device
@app.route("/am43/<action>/<grp>",methods=['GET','PUT']) ##curl -i http://localhost:5000/am43/<action>/<grp>  Send specified action to all devices in a group
def am43action(action,grp=None,dev=None):
    #Variables#
    ResultDict = {}
    if (request.method == 'PUT' and action == 'getStatus') or
       (request.method == 'GET' and action != 'getStatus'):
        return f'Method { request.method } incorrect for action { action }

    #Code#
    # Scan for BTLE devices
    try:
        #ScanForBTLEDevices()
        pass
    except:
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ERROR SCANNING FOR ALL BTLE Devices, trying to " + BlindsAction + " the blinds anyway....", flush=True)
        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Please check any open connections to the blinds motor and close them, the Blinds Engine App perhaps?", flush=True)
        pass
        #return "ERROR SCANNING FOR ALL BTLE Devices\n"
    
    # Set group list
    if grp:
        grps = [grp]
    else:
        grps = config.sections()
    
    # Loop through groups and devices
    for grp in grps:
        for blind in config[grp]:
            blindMAC = config.get(grp,blind)
            # Reset variables
            bSuccess = False

            try:
                dev = ConnectBTLEDevice(blindMAC,blind)
            except:
                print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ERROR, Cannot connect to " + blindMAC, flush=True)
                print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " Please check any open connections to the blinds motor and close them, the Blinds Engine App perhaps?", flush=True)
                continue

            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " --> Connected to " + dev.addr + ", " + blind.capitalize(), flush=True)

            BlindsControlService = dev.getServiceByUUID("fe50")
            if (BlindsControlService):
                BlindsControlServiceCharacteristic = BlindsControlService.getCharacteristics("fe51")[0]
                if (BlindsControlServiceCharacteristic):
                    if (BlindsAction == "Open" or BlindsAction == "Close" or BlindsAction == "Stop" or BlindsAction.isdigit()):
                        if (BlindsAction == "Open"):
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdMove, [0], False)
                        elif (BlindsAction == "Close"):
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdMove, [100], False)
                        elif (BlindsAction.isdigit()):
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdMove, [int(BlindsAction)], False)
                        elif (BlindsAction == "Stop"):
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdStop, [0xcc], False)

                        if (bSuccess):
                            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ----> Writing " + BlindsAction + " to " + blind.capitalize()  + " was succesfull!", flush=True)
                        else:
                            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ----> Writing to " + blind.capitalize()  + " FAILED", flush=True)

                        ResultDict.update({blind.capitalize(): [{"command":BlindsAction, "bSuccess":bSuccess, "macaddr":blind}]})

                    elif (BlindsAction == "CheckStatus"):
                        if BlindsControlServiceCharacteristic.supportsRead():
                            bSuccess = dev.setDelegate(AM43Delegate())
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdBattery, [0x01], True)
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdLight, [0x01], True)
                            bSuccess = write_message(BlindsControlServiceCharacteristic, dev, IdPosition, [0x01], True)

                            #retrieve global variables with current percentages
                            global BatteryPct 
                            global LightPct
                            global PositionPct
                            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ----> Battery level: " + str(BatteryPct) + "%, " +
                                "Blinds position: " + str(PositionPct) + "%, " +
                                "Light sensor level: " + str(LightPct) + "%", flush=True)
                            ResultDict.update({blind.capitalize(): [{"battery":BatteryPct, "position":PositionPct, "light":LightPct, "macaddr":blindMAC}]})

                            # Reset variables
                            BatteryPct = None
                            LightPct = None
                            PositionPct = None

                        else:
                            print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " ----> No reads allowed on characteristic!", flush=True)

                    else:
                        print(datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S") + " --> Unknown Blindsaction command: " + BlindsAction, flush=True)
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

