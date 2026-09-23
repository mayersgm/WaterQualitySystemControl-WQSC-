"""
WATER QUALITY CONTROL SYSTEM (TDS)ppm
"""

# Standard Library
from machine import Pin, I2C, Timer, ADC, WDT
import math
import sys, os
import _thread
import time
from I2C_Responder import I2CResponder
import json


RESPONDER_I2C_DEVICE_ID = 0
RESPONDER_ADDRESS = 0x41
GPIO_RESPONDER_SDA = 0
GPIO_RESPONDER_SCL = 1
BUFFER_SIZE = 128  # Increased buffer size
NONE = 0

led = Pin(25, Pin.OUT)
LED_state = True
tyme = Timer()
Valve_Timer = Timer()

State = 0
next_state = State
start_switch_state = 0
stirilize_switch_state = 0
flush_switch_state = 0
empty_switch_state = 0
reset_switch_state = 0
busy_state = 0
process_time = 0
refillTimer = 1
fillTimer = 2
fill_switch_state = 2
cooling_fan_state = 0
Refill_Vl = 0
Drain_Vl  = 1
Pwr_sw    = 2
Fan_sw    = 3
Res_lim   = 4 # and 5
B_limL    = 6
B_limH    = 7

BOILER_TANK_LIMIT_HI    = Pin(11,Pin.IN, Pin.PULL_UP)  # Input from BOILER_TANK_LIMIT_HI
BOILER_TANK_LIMIT_LO    = Pin(10,Pin.IN, Pin.PULL_UP)  # Input from BOILER_TANK_LIMIT_LO
RESERVOIR_TANK_LIMIT_HI = Pin(12,Pin.IN, Pin.PULL_UP)  # Input from ReservoirTank_T
RESERVOIR_TANK_LIMIT_LO = Pin(13,Pin.IN, Pin.PULL_UP)   # Input from ReservoirTank_B
CALIBRATE_TDS_OFFSET    = Pin(2,Pin.IN, Pin.PULL_UP)   # Input from ReservoirTank_B
WATER_FLOW_SW           = Pin(28,Pin.IN, Pin.PULL_UP)   # 
BOILER_REFILL_VALVE     = Pin(18,Pin.OPEN_DRAIN)   # Output to SOLENOID_BOILER_REFILL_VALVE
BOILER_WATER_VALVE      = Pin(19,Pin.OPEN_DRAIN)   # Output to BOILER_MAIN_WATER_VALVE
#BOILER_DRAIN_VALVE      = Pin(21,Pin.OPEN_DRAIN)   # Output to BOILER_DRAIN_VALVE and Pump
BOILER_POWER            = Pin(16,Pin.OUT,Pin.PULL_DOWN)   # Output to BiolerPower switch
#COOLING_FAN             = Pin(17,Pin.OUT,Pin.PULL_DOWN)   # Output to BiolerStirilization switch

# Setup pin 0:3 as an output that's at a high logic level default
BOILER_REFILL_VALVE.value(True)
#BOILER_DRAIN_VALVE.value(True)# NOT USED
BOILER_WATER_VALVE.value(True)
BOILER_POWER.value(False)
#COOLING_FAN.value(True)

#BUFF_SIZE = 30  # Buffer size for median filtering


DEBUG = False
buffer_size = 13#

'''************'''
value =0
REFILL_VALVE = 0
DRAIN_VALVE =1
BOILER_PWR = 2
FAN = 3
RESERVOIR = 4
ERROR = 5
BOILER_LEVEL = 6
WATER_FLOW = 8
CYCLE_CNT = 11
REFILL_TIMER = 12

ON = 0
OFF = 1
OPEN = 0
CLOSE = 1
_OPEN = 1
TEMP_LIMIT1 = 150.0 # >= 141 Deg F
TEMP_LIMIT2 = 170.0
#boiler levels
MIN_LIMIT = 0x02
MID_LIMIT = 0x03
MAX_LIMIT = 0x01
MIN_TIME_LIMIT = 10
MID_TIME_LIMIT = 5

#Reservoir levels
FULL = 0x03
FIRST_LEVEL  = 0X02
SECOND_LEVEL = 0X01
BELOW_LEVEL  = 0X00
RESET = 0x16

# commands
RUN = 0x11          #autonomous mode
START = 0x12        #Start water distillation
STANDBY = 0x13      #Stop water distillation
STOP = 0x14         #discontinue any function
STERILIZE = 0x15    #Start tank steriliation
EMPTY = 0x16        #empty boiler tank for cleaning
RESET = 0x17        #re-initialize pico
bufferSize = 1024
cycle_count = 0
BUFF_SIZE= 30
#Boiler refill time out
T_SHORT = 30 #Normal refill cycle in seconds
T_LONG = 300 #Empty Tank refill cycle in seconds

status_reg =  {"CMD":START,             #Distiller control command
               "TEMP":0,      			#Boiler Temperature
               "TDS": 0,      			#water quality measurement
               "CYCLE_CNT":cycle_count, #system cycle count
               "REFILL_TIMER":0x0,      #Boiler tank refill time out
               "REFILL_VALVE":False,    #Boiler refil valve
               "RESERVOIR":0x03,        #Distiller distilled reservoir
               "DRAIN_VALVE": 0,        #Boiler drain valve
               "BOILER_LEVEL":0,        #Boiler water level sensor
               "BOILER_PWR":0,          #Boiler power control relay
               "WATER_FLOW":1           #Distiller cooling fan control relay
               }

class Wqcs_Mcu():
    def __init__(self):
        self.buffersize = buffer_size
        self.analogBuff = [0] * BUFF_SIZE
        self.analogBufferTemp = [0] * BUFF_SIZE
        self.temp_f = 0.0
        self.tds = 0.0

        self.i2c_com = I2CResponder(
            RESPONDER_I2C_DEVICE_ID, 
            sda_gpio=GPIO_RESPONDER_SDA, 
            scl_gpio=GPIO_RESPONDER_SCL, 
            responder_address=RESPONDER_ADDRESS
        )       
        self.pi = PyPicoIO()
        self.i2cSlave = I2C_Slave(self.i2c_com)
        self.sensor = Sensors(self)

         # Load or perform calibration
        self.sensor.calibrate_tds()
        if bool(CALIBRATE_TDS_OFFSET.value()) == 0: self.sensor.force_recalibration()
        #self.tds = self.sensor.calculate_tds()
        

        self.i2cSlave.set_wqcs(self)
        self.startprocess()

    def get_system_status(self):
        """Get system status with string temperature"""
        try:
            # Get values
            self.temp_f = self.sensor.read_temperature()  # Already a string
            # Create status dict
            status = {
                "t": self.temp_f,
                "d": self.tds,
                "b": status_reg["BOILER_PWR"],
                "r": self.get_reservoir_level(), #self.reservoir_status(),#
                "f": status_reg["WATER_FLOW"],
                "ref_active": status_reg["REFILL_VALVE"],  # Refill active flag
                "ref_count": status_reg["REFILL_TIMER"],   # Refill countdown
                "e": status_reg.get("ERROR", 0)
            }
            
            # Update status_reg
            status_reg["TEMP"] = self.temp_f
            status_reg["TDS"] = self.tds
            
           # print("STATUS",status)
            return status
            
        except Exception as e:
            print(f"Status generation error: {e}")
            return {"e": 1, "ref_active": False, "ref_count": 0}

    def get_reservoir_level(self):
        """Get reservoir level (0-3)"""
        try:
            if self.pi.pico2040(RESERVOIR) == FULL:
                return 3  # Full
            elif self.pi.pico2040(RESERVOIR) == FIRST_LEVEL:
                return 2  # Medium
            elif self.pi.pico2040(RESERVOIR) == SECOND_LEVEL:
                return 1  # Low
            else:
                return 0  # Empty
        except Exception as e:
            print(f"Reservoir level error: {e}")
            return 0

    def startprocess(self):
        self.pi.debug("Initialize pico to default state", None)
        self.pi.debug("Turn off boiler", NONE)
        self.pi.pico2040(BOILER_PWR, False)
        #status_reg["BOILER_PWR"]= False         #Boiler power control relay
        self.pi.debug("Close Drain valve", NONE)
        self.pi.pico2040(DRAIN_VALVE, CLOSE)
        status_reg["DRAIN_VALVE"]= CLOSE       #Boiler drain valve
        self.pi.debug("Close refill valve", NONE)
        status_reg["REFILL_VALVE"]=False       #Boiler refil valve
        self.pi.debug("Turn off Cooling fan", NONE)
        self.pi.pico2040(FAN, False)
        status_reg["FAN"]= False                #Distiller cooling fan control relay
        time.sleep(0.5)
        #status_reg["REFILL_TIMER"]=0x0         #Boiler tank refill time out
        #status_reg["RESERVOIR"]=0x03           #Distiller distilled reservoir
        #status_reg["BOILER_LEVEL"]=0           #Boiler water level sensor
        
       
 
        
        
        self.pi.debug("Start running i2c slave on 2nd core", None)
        time.sleep(0.5)VREF
        _thread.start_new_thread(self.i2cSlave.get_i2c_cmd,())
        time.sleep(0.5)
        self.get_system_status()
        while True:
            print("******* Running Distiller *******", None)
            time.sleep(.5)
            self.distillation_process()     

    def distillation_process(self):
        global buffer_in
        cycle_count = 0
        valvetimer = 0
        cooling_fan_state = False
        old_status_reg = status_reg

        """
        The state which activates and monitor
        the boiler(State) process.
        """
        next_state = 0
        state = next_state

        boiler_state = 2
        """
        The state which activates and deactivates
        the boiler(State) process.
        """
        boiler_waterlevel_state = 6
        """
        The state which checks boiler tank water level,activates and
        monitor the refill process.
        """
        reservoir_waterlevel_state  = 4 
        """
        The state which checks the reservoir water level, activates and monitor
        the distillationProcess(State) process.
        """
        coolingfan_state = 3
        """
        The state which activates and deactivates
        the COOLING_FAN(State) process.
        """
        system_status_state = 8
        """
        The state which report boiler temperature, TDS data(water quality ppm).
        boiler status(on/off, water level)
        """
        self.coolingfan_state = coolingfan_state
        self.system_status_state =  system_status_state
        self.reservoir_waterlevel_state =  reservoir_waterlevel_state
        self.boiler_waterlevel_state =  boiler_waterlevel_state

    
        next_state = system_status_state
        while True:
            self.tds = self.sensor.calculate_tds()
            self.tds_status()
            #uncomment to debug without PyPortal
            #self.get_system_status()
            cycle_count+=1

           # print("STATUS_REG",status_reg)

            state = next_state
            self.pi.debug("Next State is",State, next_state)

            #*********BOILER WATER LEVEL STATE**********
            if state == boiler_waterlevel_state:
                self.pi.debug("Check boilerTank Level",status_reg)
                if self.pi.pico2040(BOILER_LEVEL)== MIN_LIMIT:
                    status_reg["BOILER_LEVEL"] = MIN_LIMIT
                    if self.reservoir_status()!= FULL:
                        self.refill_boiler(t = T_LONG) #set refill timer for 5 min
                        next_state = boiler_waterlevel_state

                elif self.pi.pico2040(BOILER_LEVEL)== MID_LIMIT:
                        if self.reservoir_status()!= FULL:
                            status_reg["BOILER_LEVEL"]= MID_LIMIT
                            self.refill_boiler(t = T_SHORT) #set refill timer for 5 Sec
                            next_state = boiler_waterlevel_state            

                elif self.pi.pico2040(BOILER_LEVEL)== MAX_LIMIT:
                    status_reg["BOILER_LEVEL"]= MAX_LIMIT
                    self.pi.debug("boilerTank is FULL!!",status_reg)
                    if self.waterflow_status == ON:
                        self.pi.debug("Water flow is ON!!",status_reg)
                        self.boiler_on(False) # shut off boiler
                        status_reg["BOILER_PWR"]= False
                        time.sleep(.1)
                        self.pi.debug("Turn off Boiler",status_reg)
                        next_state = boiler_state
                    else:
                        next_state = reservoir_waterlevel_state 
                else: 
                       next_state = system_status_state
                    #    time.sleep(0.1)

            #*********RESERVOIR WATER LEVEL STATE**********    
            elif state == reservoir_waterlevel_state :
                if bool(BOILER_POWER.value())== True:
                    self.pi.debug("Boiler is currently on!!",status_reg)
                    status_reg["BOILER_PWR"]= 1
                    time.sleep(.1)
                    self.reservoir_status()
                    next_state = coolingfan_state
                else:
                    if self.reservoir_status()== 1:
                        next_state = system_status_state

                    #elif status_reg["CMD"]== (RUN or STANDBY):
                   #     self.boiler(ON)
                    #    next_state = system_status_state

            #*********COOLING FAN STATE**********
            elif state == coolingfan_state:
                if status_reg["TEMP"]<= str(TEMP_LIMIT1):
                   # self.pi.pico2040(FAN, True)
                    #status_reg["FAN"]= True
                    self.pi.debug("Turn on Cooling fan",status_reg) 
                    self.pi.debug("Water temp raw value:",value)
                    time.sleep(.1)

                next_state = system_status_state

            #*********SYSTEM STATUS STATE**********
            elif state == system_status_state:
                next_state = self.cmd_status(next_state)
                self.pi.debug("No of loops thru states",cycle_count)
                '''
                if status_reg["BOILER_PWR"]== 0:
                    self.reservoir_status()
                    next_state = boiler_waterlevel_state
                '''
                        
    def refill_boiler(self, t=10):
       
        valvetimer = t #wait t seconds for water to reach limit with pump
        valve_period = t
        status_reg["REFILL_TIMER"]= valve_period
        self.pi.pico2040(REFILL_VALVE, OPEN)
        valve_period = t
        while self.pi.pico2040(BOILER_LEVEL)!= MAX_LIMIT:       
            valvetimer -= 1
            #if valvetimer >= 5: self.wdt.feed() #Reset WDT

            print("MID Valve Timer Satus",valvetimer, valve_period)
            time.sleep(1)

            #status_reg["REFILL_TIMER"]= valvetimer
                #time.sleep(2)
                #Valve_Timer.init(period=5000, mode=Timer.PERIODIC , callback= self.valve_close)
            
            if valvetimer <1:
                self.pi.pico2040(REFILL_VALVE, CLOSE)
  
            if valvetimer <= 0:
               self.refill_error()
                #wait for WDT to time out
            
        self.pi.pico2040(REFILL_VALVE, CLOSE)  
        status_reg["REFILL_VALVE"]= False        
        return
    
    def delay(self,t):
        while t >= 1:
            #print("DELAY Satus",t)
            #self.wdt.feed()
            time.sleep(1)
            t-=1
        return
    
    def refill_error(self):
        '''Midigate Possible overflow or flood condition'''
        self.pi.pico2040(REFILL_VALVE, CLOSE)
        status_reg["REFILL_VALVE"]= False    
        self.boiler_on(False)
        while  True:
            status_reg["ERROR"]=True
            time.sleep(1)
            #self.wdt.feed() #Reset WDT

    def empty_boiler(self):
        self.boiler_on(False)
        self.pi.pico2040(DRAIN_VALVE, OPEN)

        while status_reg["CMD"] == EMPTY: 
            #self.wdt.feed() #reset wdt
            time.sleep(1)
    
        self.pi.pico2040(DRAIN_VALVE, CLOSE)
        status_reg["DRAIN_VALVE"]= OFF
        return 0

    def boiler_on(self, sw=False):
        if sw == True:
            if bool(BOILER_POWER.value())== False:
                self.pi.debug("Turn on boiler",status_reg)
                self.pi.pico2040(BOILER_PWR, sw)
                status_reg["BOILER_PWR"]= sw
        elif sw == False:
                self.pi.pico2040(BOILER_PWR, sw)
                self.pi.debug("Turn off boiler",status_reg)
                status_reg["BOILER_PWR"]= sw
                self.pi.debug("Turn Cooling Fan off",status_reg)
                self.pi.pico2040(FAN, sw)
                status_reg["FAN"]= sw

    def reservoir_status(self):
        res_status = self.get_reservoir_level()
        if status_reg["CMD"]!= STOP or EMPTY:
            if res_status == 3:
                status_reg["RESERVOIR"]= FULL
                self.pi.debug("Res_Water Full",status_reg)
                time.sleep(.5)
                self.boiler_on(False)
                status_reg["FAN"]= False
                #status_reg["CMD"]= STANDBY #/STANDBY
                time.sleep(.1)

            else:
                status_reg["RESERVOIR"]= res_status #BELOW_LEVEL
                self.pi.debug("Next State is",State, next_state)
                if status_reg["CMD"] == START or STANDBY:
                    self.boiler_on(True)  
                    status_reg["FAN"]= True  
                    #print("STATUS2...",res_status, status_reg["CMD"])
            return res_status
        else:
            self.boiler_on(False)
            return res_status
        
    def cmd_status(self,current_state):
        next_state = current_state
        #print("STATUS_REG",status_reg)
        if status_reg["CMD"] == START:
            if status_reg["RESERVOIR"]!= FULL:
                self.reservoir_status()
                next_state = self.boiler_waterlevel_state # coolingfan_state
                self.pi.debug("DISTILLATION MODE..............",cycle_count)
            else:
                next_state = self.reservoir_waterlevel_state 

        elif status_reg["CMD"]==  STOP:
            if bool(BOILER_POWER.value())== True: self.boiler_on(False)
            #print("STANNDBY MODE..............",cycle_count)
            next_state = self.system_status_state

        elif status_reg["CMD"]==  RUN:
            if bool(BOILER_POWER.value())== False:
                self.reservoir_status()
                self.pi.debug("RUN MODE..............",cycle_count)
                next_state = self.system_status_state
            else:
                next_state = self.boiler_waterlevel_state

        elif status_reg["CMD"]== STERILIZE:
            self.boiler_on(True)
            if status_reg["FAN"]== True:
                self.pi.pico2040(FAN, False)
                status_reg["FAN"]= False

            next_state = self.system_status_state
            self.pi.debug("STERILIZE MODE..............",cycle_count)
        
        elif status_reg["CMD"]== EMPTY:
            time.sleep(2)
            self.empty_boiler()
            next_state = self.system_status_state

        elif status_reg["CMD"]==  RESET: 
            self.pi.debug("Initialize pico to default state", None)
           # self.pi.debug("Turn off boiler", NONE)
           # self.pi.pico2040(BOILER_PWR, False)
            self.pi.debug("Close Drain valve", NONE)
            self.pi.pico2040(DRAIN_VALVE, OFF)
            self.pi.debug("Close refill valve", NONE)
            self.pi.pico2040(REFILL_VALVE, CLOSE)
            #self.pi.debug("Turn off Cooling fan", NONE)
            #self.pi.pico2040(FAN, False)
            next_state = self.boiler_waterlevel_state

        return next_state

    def tds_status(self):
        '''Midigate Possible reservior contamination '''
        self.tds = self.sensor.calculate_tds()
        if self.tds >= 50:  
            self.boiler_on(False)
            self.pi.pico2040(REFILL_VALVE, CLOSE)
            while  True:
                status_reg["ERROR"]=True
                time.sleep(1)

    def waterflow_status(self):
        """Get water flow  (0/1)"""
        try:
            if self.pi.pico2040(WATER_FLOW) == 1:
                return 1  # close
            else: return 0  # open
        except Exception as e:
            print(f"flow status unknown : {e}")
            return None

class I2C_Slave:
    def __init__(self, slave):
        self.i2c_slave = slave
        self.hexformat = HexFormat()
        self.lock = _thread.allocate_lock()
        self.wqcs = None  # Will be set by Wqcs_Mcu
        self.buffer_size = BUFFER_SIZE
        self.status_reg = status_reg
    
    def set_wqcs(self, wqcs):
        self.wqcs = wqcs
     
    def tick(self, timer):
        l = timer
        global led, LED_state
        LED_state = not LED_state
        led.value(LED_state)
##********************************

    def get_i2c_cmd(self):
        print("Waiting for command")
        
        while True:
            tyme.init(period=1000, mode=Timer.PERIODIC, callback=self.tick)
            
            try:
                # Wait for read request
                while not self.i2c_slave.read_is_pending():
                    pass
                
                # Get command if there's data to read
                if self.i2c_slave.write_data_is_available():
                    cmd_data = self.i2c_slave.get_write_data(1)
                    #print(f"CMD FROM PORTAL: {cmd_data}")
                    if cmd_data:
                        status_reg["CMD"] = cmd_data[0]
                    
                # Get status and create JSON
                if self.wqcs:
                    status = self.wqcs.get_system_status()
                    json_str = json.dumps(status)  # No need for compact JSON now
                else:
                    json_str = '{"t":"0.0","d":0,"b":0,"r":0,"f":1}'
               
                print("CMD FROM PORTAL:", status_reg["CMD"])
                print(f"Sending JSON: {json_str}")
                print(f"JSON length: {len(json_str)}")
                
                
                # Pad with zeros using larger buffer
                padded_data = bytearray(BUFFER_SIZE)
                json_bytes = json_str.encode('utf-8')
                if len(json_bytes) > BUFFER_SIZE - 1:  # Leave room for null terminator
                    print("Warning: JSON too long, will be truncated")
                padded_data[:len(json_bytes)] = json_bytes
                
                # Send each byte
                for b in padded_data:
                    self.i2c_slave.put_read_data(b)
                    
            except Exception as e:
                print(f"I2C error: {e}")
                error_json = '{"t":"0.0","d":0,"b":0,"r":0,"f":1}'
                error_data = bytearray(BUFFER_SIZE)
                error_bytes = error_json.encode('utf-8')
                error_data[:len(error_bytes)] = error_bytes
                
                for b in error_data:
                    self.i2c_slave.put_read_data(b)
            
            time.sleep(0.1)

class PyPicoIO(object): 
    def __init__(self):
        self.status_reg = status_reg
        self.hexformat = HexFormat()
        #self.thread_lock = _thread.allocate_lock()

    def pico2040(self,port=8, cmd=0):
        self.port = port
        self.cmd = cmd

        SystemError = 0

        ''' 
        #*******ports:************
        #Refill_Valve    = 0
        #Drain_Valve     = 1
        #boilerPwr_sw    = 2
        #COOLING_FAN_sw   = 3
        #WaterRes_upperlim  = 4
        #WaterRes_lowerlim  = 5
        #boiler_lowerlim = 6
        #boiler_upperlim = 7
        #WaterFlow = 8
        #*************************
        '''
        self.debug("Port&Cmd",self.port, self.cmd)

        try:
            if self.port == 0:#Open/Close BOILER_REFILL_VALVE
                BOILER_REFILL_VALVE.value(self.cmd)
                time.sleep(0.5)
                if bool(BOILER_REFILL_VALVE.value()) == OPEN:
                    status_reg["REFILL_VALVE"]= True
                else:
                    status_reg["REFILL_VALVE"]= False
                self.debug("Open/Close boiler Refill Valve!!:", self.cmd)

            if self.port == 1:#Open/Close BOILER_DRAIN_VALVE
                BOILER_DRAIN_VALVE.value(self.cmd)
                time.sleep(0.5)
                #with self.thread_lock:
                if bool(BOILER_DRAIN_VALVE.value()) == OPEN:
                    status_reg["DRAIN_VALVE"]= True
                else:
                    status_reg["DRAIN_VALVE"]= False


                self.debug("Open/Close boiler Drain Valve",self.cmd)

            if self.port == 2: #Turn BOILER_POWER fan Off/On 
                BOILER_POWER.value(self.cmd)
                BOILER_WATER_VALVE.value(not self.cmd)
                self.debug("Turn boiler Power and water supply valve Off/On ",self.cmd)

            if self.port == 3:#Turn Cooling fan Off/On 
                COOLING_FAN.value(self.cmd)
                self.debug("Turn Cooling fan Off/On ",self.cmd)

            if self.port == 4:#Read Reservoir Tank level
                self.debug("Read Reservoir Tank levels",self.cmd)
                
                if RESERVOIR_TANK_LIMIT_LO.value() == 1:
                    if RESERVOIR_TANK_LIMIT_HI.value() == 1:
                        return 3
                    else:
                        return 1
                elif RESERVOIR_TANK_LIMIT_HI.value() ==1:
                    return 2
                else:
                    return 0
                self.debug("Read Reservoir Tank levels", buffer_out[2])    
        
            if self.port == 6:#Read boilerTank Bottom Limit switch
                if BOILER_TANK_LIMIT_LO.value() == 1:
                    if BOILER_TANK_LIMIT_HI.value() == 1:
                        self.debug("Read boiler Tank levels",3)   
                        return 3
                    else:
                        return 1
                elif BOILER_TANK_LIMIT_HI.value() ==1:
                    self.debug("Read boilerTank levels",2) 
                    return 2
                else:
                    self.debug("Read boiler Tank levels",0) 
                    return 0
            
            if self.port == 8:#Read boilerTank Bottom Limit switch
                if WATER_FLOW_SW.value() == 1:
                    self.debug("Read water flow",1)   
                    return 1
                else:
                    return 0
            
            else:
                    self.debug("Move along..Nothing to see here!!",0)

            #return status_reg

        except OSError:
            SystemError = True
            return SystemError
        
    def debug(self, message,Ivar1,Ivar2=0):
        if DEBUG == True:
            time.sleep(0.1)
            print(message, Ivar1, Ivar2)
            time.sleep(0.1)  
  
class HexFormat:
    def __init__(self, _object=0):
        self._object = _object

    def format_hex(self, _object):
        """Format a value or list of values as 2 digit hex."""
        try:
            values_hex = [self.to_hex(value) for value in _object]
            return '[{}]'.format(', '.join(values_hex))
        except TypeError:
            # The object is a single value
            return self.to_hex(_object)


    def to_hex(self, value=0):
        return '0x{:02X}'.format(value) 

class Sensors:
    def __init__(self, pin_number, vref=3.26, series_resistance=100000, high_side_ntc=False,
                 beta=3950, nominal_resistance=50000, nominal_temp=25):
        """
        Initialize NTC thermistor reading on specified ADC pin
        
        Args:
            pin_number (int): GPIO pin number connected to the voltage divider
            vref (float): ADC reference voltage (default 3.26V)
            series_resistance (float): Value of the series resistor in ohms (default 10k)
            high_side_ntc (bool): If True, NTC is connected to Vref (high-side)
                                 If False, NTC is connected to GND (low-side)
            beta (float): Beta coefficient of the NTC (default 3950)
            nominal_resistance (float): Resistance at nominal temperature (default 50k)
            nominal_temp (float): Nominal temperature in Celsius (default 25°C)
        """
        self.debug = False
        self.temp_adc = ADC(26)
        self.tds_adc  = ADC(28)
        self.vref = vref
        self.adc_res = 65535
        self.series_resistance = series_resistance
        self.high_side_ntc = high_side_ntc
        
        # NTC thermistor parameters
        self.beta = beta 
        self.nominal_temp = nominal_temp
        self.nominal_resistance = nominal_resistance

         # TDS parameters
        self.analogBuff = [0] * BUFF_SIZE
        self.analogBufferTemp = [0] * BUFF_SIZE
        self.MIN_VALID_VOLTAGE = 0.1
    
    def read_temperature(self, num_samples=10):
        """
        Read temperature from NTC thermistor
        
        Args:
            num_samples (int): Number of readings to average (default 10)
            
        Returns:
            float: Temperature in Celsius, or None if reading is outside valid range
        """
        try:
            # Take multiple readings and average them
            adc_sum = 0
            for _ in range(num_samples):
                adc_sum += self.temp_adc.read_u16()
            adc_value = adc_sum / num_samples
            
            # Convert ADC reading to voltage using actual Vref
            voltage = (adc_value / self.adc_res) * self.vref
            
            # Debug output
            #print(f"ADC Value: {adc_value:.0f}")
            #print(f"Voltage: {voltage:.3f}V")
            
            # Calculate resistance of thermistor based on configuration
            if self.high_side_ntc:
                # High-side NTC configuration
                if voltage == 0:
                    return None
                thermistor_resistance = self.series_resistance * ((self.vref / voltage) - 1)
            else:
                # Low-side NTC configuration
                if voltage == self.vref:
                    return None
                thermistor_resistance = self.series_resistance * (voltage / (self.vref - voltage))
            

            # Steinhart-Hart equation to convert resistance to temperature
            steinhart = math.log(thermistor_resistance / self.nominal_resistance) / self.beta
            steinhart += 1.0 / (self.nominal_temp + 273.15)
            temperature = (1.0 / steinhart) - 273.15
            celsius = temperature
            fahrenheit = (celsius * 9/5) + 32

            # Debug output
            if self.debug == True:
                print(f"Thermistor Resistance: {thermistor_resistance:.0f} ohms")
                print(f"Celsius: {celsius:.3}°C")
                print(f"Fahrenheit: {fahrenheit:.3}°F")

            # Check if temperature is within valid range
            if -10 <= temperature <= 150:
                return "{:.1f}".format(fahrenheit)
            else:
                return None
                
        except Exception as e:
            print(f"Error reading temperature: {e}")
            return None

    def getMedianNum(self,iFilterLen):
        """
        Computes the median value from the analogBufferTemp list.
        """

        for j in range(iFilterLen - 1):
            for i in range(iFilterLen - j - 1):
                if self.analogBufferTemp[i] > self.analogBufferTemp[i + 1]:
                    # Swap values
                    self.analogBufferTemp[i], self.analogBufferTemp[i + 1] = self.analogBufferTemp[i + 1], self.analogBufferTemp[i]

        if iFilterLen % 2 == 1:  # Odd length
            return float(self.analogBufferTemp[iFilterLen // 2])
        else:  # Even length
            mid = iFilterLen // 2
            return (self.analogBufferTemp[mid] + self.analogBufferTemp[mid - 1]) / 2.0

    def calculate_tds(self):
        """
        Reads and calculates TDS (ppm) using median filtering and temperature compensation.
        """
        TDS_FACTOR = 0.5  # Conversion factor for TDS
        TEMPERATURE = 25.0  # Default temperature (replace with a sensor if available)

        try:
            # Initialize analogBufferIndex if it doesn't exist
            if not hasattr(self, 'analogBufferIndex'):
                self.analogBufferIndex = 0

            # Fill the analog buffer
            for _ in range(BUFF_SIZE):
                self.analogBuff[self.analogBufferIndex] = self.tds_adc.read_u16()
                self.analogBufferIndex = (self.analogBufferIndex + 1) % BUFF_SIZE
                time.sleep(0.04)  # Sampling delay
                #print("ANALOG_BUFF", self.analogBuff)
                #print("ANALOG_BUFF_index", self.analogBufferIndex)

            # Copy buffer values for sorting
            for i in range(BUFF_SIZE):
                self.analogBufferTemp[i] = self.analogBuff[i]

            # Get median voltage
            median_adc_value = self.getMedianNum(BUFF_SIZE)
            voltage = (median_adc_value / self.adc_res) * self.vref
            
            voltage -= self.offset_voltage

            if voltage <= 0.005:
                voltage = 0.00

            Vt = self.tds_adc.read_u16()/self.adc_res*self.vref
            # Temperature compensation
            compensation_coefficient = 1.0 + 0.02 * (TEMPERATURE - 25.0)
            compensated_voltage = voltage / compensation_coefficient

            # TDS calculation using polynomial equation
            tds_value = (
                133.42 * compensated_voltage**3
                - 255.86 * compensated_voltage**2
                + 857.39 * compensated_voltage
            ) * TDS_FACTOR
            if tds_value < self.MIN_VALID_VOLTAGE: tds_value = 0.00
            
            if self.debug == True:
                print("TDS = ",tds_value, voltage, self.offset_voltage,  Vt)

            return tds_value
        
        except Exception as e:
            print(f"TDS calculation error: {e}")
            return 0

    def save_calibration(self, offset_value):
        """Save TDS offset calibration to flash"""
        try:
            # Convert float to string with 6 decimal places
            offset_str = f"{offset_value:.6f}"
            
            # Write to file
            with open("tds_cal.txt", "w") as f:
                f.write(offset_str)
                
            print(f"Saved calibration offset: {offset_str}")
            
        except Exception as e:
            print(f"Error saving calibration: {e}")

    def load_calibration(self):
        """Load TDS offset calibration from flash"""
        try:
            # Check if calibration file exists
            if "tds_cal.txt" in os.listdir():
                with open("tds_cal.txt", "r") as f:
                    offset_str = f.read().strip()
                    offset_value = float(offset_str)
                    print(f"Loaded calibration offset: {offset_value:.6f}")
                    return offset_value
            else:
                print("No calibration file found")
                return None
                
        except Exception as e:
            print(f"Error loading calibration: {e}")
            return None

    def calibrate_tds(self):
        """Calibrate TDS sensor by reading baseline noise"""
        # First try to load existing calibration
        loaded_offset = self.load_calibration()
        if loaded_offset is not None:
            self.offset_voltage = loaded_offset
            return
            
        print("Performing new TDS calibration...")
        total = 0
        samples = 20
        
        # Take multiple readings with delays
        for _ in range(samples):
            total += self.tds_adc.read_u16()
            time.sleep(0.1)
        
        self.offset_voltage = ((total / samples) / self.adc_res) * self.vref
        
        # Save the new calibration
        self.save_calibration(self.offset_voltage)
        print(f"New calibration offset: {self.offset_voltage:.6f}V")
        
    def force_recalibration(self):
        """Force a new TDS sensor calibration"""
        try:
            # Delete existing calibration file if it exists
            if "tds_cal.txt" in os.listdir():
                os.remove("tds_cal.txt")
        except:
            pass
        print("Force a new TDS sensor calibration")    
        # Perform new calibration
        self.calibrate_tds()

# Example usage:
"""
thermistor = NTCThermistor(
    pin_number=26,
    vref=3.26,               # Measured reference voltage
    series_resistance=100000,  # 100k series resistor
    high_side_ntc=False,     # NTC connected to ground
    beta=3950,               # Beta value
    nominal_resistance=50000  # 57k at 25°C
)

# Read temperature
temp = thermistor.read_temperature()
if temp is not None:
    print(f"Temperature: {temp}°C")
else:
    print("Temperature reading out of range or error")
"""
if __name__ == "__main__":
    #cmd = 0
    Wqcs_Mcu()# Write your code here :-)


