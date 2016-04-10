#!/usr/bin/env python

"""
    A Python driver for the Arduino microcontroller running the
    ROSArduinoBridge firmware.
    
    Created for the Pi Robot Project: http://www.pirobot.org
    Copyright (c) 2012 Patrick Goebel.  All rights reserved.

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.
    
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details at:
    
    http://www.gnu.org/licenses/gpl.html

"""

import thread
from math import pi as PI
import os
import time
import sys, traceback
from serial.serialutil import SerialException
import serial

class Arduino:
    def __init__(self, port="/dev/ttyUSB0", baudrate=57600, timeout=0.5):
        
        self.PID_RATE = 30 # Do not change this!  It is a fixed property of the Arduino PID controller.
        self.PID_INTERVAL = 1000 / 30
        
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.encoder_count = 0
        self.writeTimeout = timeout
    
        # Keep things thread safe
        self.mutex = thread.allocate_lock()

    def connect(self):
        try:
            print "Connecting to Arduino on port", self.port, "..."
            
            # The port has to be open once with the default baud rate before opening again for real
            self.serial_port = serial.Serial(port=self.port)
          
            # Needed for Leonardo only
            while not self.port:
                time.sleep(self.timeout)

            # Now open the port with the real settings
            self.serial_port = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout, writeTimeout=self.writeTimeout)

            # Test the connection by reading the baudrate
            test = self.get_baud()
            if test != self.baudrate:
                time.sleep(self.timeout)
                test = self.get_baud()   
                if test != self.baudrate:
                    raise SerialException
            print "Connected at", self.baudrate
            print "Arduino is ready."

        except SerialException:
            print "Serial Exception:"
            print sys.exc_info()
            print "Traceback follows:"
            traceback.print_exc(file=sys.stdout)
            print "Cannot connect to Arduino!"
            os._exit(1)

    def open(self): 
        ''' Open the serial port.
        '''
        self.serial_port.open()

    def close(self): 
        ''' Close the serial port.
        '''
        self.serial_port.close() 
    
    def send(self, cmd):
        ''' This command should not be used on its own: it is called by the execute commands
            below in a thread safe manner.
        '''
        self.serial_port.write(cmd + '\r')

    def execute(self, cmd, max_attempts=5):
        ''' Thread safe execution of "cmd" on the Arduino returning a single value.
        '''
        self.mutex.acquire()

        self.serial_port.write(cmd + '\r')
        
        value = self.serial_port.readline().strip('\n')
        
        self.mutex.release()

        return value

    def execute_array(self, cmd, max_attempts=5):
        ''' Thread safe execution of "cmd" on the Arduino returning an array.
        '''
        values = self.execute(cmd, max_attempts).split()

        return values

    def execute_ack(self, cmd, max_attempts=5):
        ''' Thread safe execution of "cmd" on the Arduino returning True if response is ACK.
        '''
        ack = self.execute(cmd, max_attempts)
        
        return ack == 'OK'
    
    def update_pid(self, Kp, Kd, Ki, Ko):
        ''' Set the PID parameters on the Arduino
        '''
        print "Updating PID parameters"
        cmd = 'u ' + str(Kp) + ':' + str(Kd) + ':' + str(Ki) + ':' + str(Ko)
        self.execute_ack(cmd)                          

    def get_baud(self):
        ''' Get the current baud rate on the serial port.
        '''
        try:
            return int(self.execute('b', max_attempts=5))
        except:
            return None

    def get_encoder_counts(self):
        values = self.execute_array('e')
        if len(values) != 2:
            print "Encoder count was not 2"
            raise SerialException
            return None
        else:
            return map(int, values)

    def reset_encoders(self):
        ''' Reset the encoder counts to 0
        '''
        return self.execute_ack('r')

    def get_imu_data(self):
        '''
        IMU data is assumed to be returned in the following order:
    
        [ax, ay, az, gx, gy, gz, mx, my, mz, roll, pitch, uh]
    
        where a stands for accelerometer, g for gyroscope and m for magnetometer.
        The last value uh stands for "unified heading" that some IMU's compute
        from both gyroscope and compass data.
        '''
        values = self.execute_array('i')
        if len(values) != 12:
            print "IMU data incomplete!"
            return None
        else:
            return map(float, values)

    def drive(self, right, left):
        ''' Speeds are given in encoder ticks per PID interval
        '''
        return self.execute_ack('m %d %d' %(right, left))
    
    def drive_m_per_s(self, right, left):
        ''' Set the motor speeds in meters per second.
        '''
        left_revs_per_second = float(left) / (self.wheel_diameter * PI)
        right_revs_per_second = float(right) / (self.wheel_diameter * PI)

        left_ticks_per_loop = int(left_revs_per_second * self.encoder_resolution * self.PID_INTERVAL * self.gear_reduction)
        right_ticks_per_loop  = int(right_revs_per_second * self.encoder_resolution * self.PID_INTERVAL * self.gear_reduction)

        self.drive(right_ticks_per_loop , left_ticks_per_loop )
        
    def stop(self):
        ''' Stop both motors.
        '''
        self.drive(0, 0)
        
    def analog_pin_mode(self, pin, mode):
        return self.execute_ack('c A%d %d' %(pin, mode))
            
    def analog_read(self, pin):
        try:
            return int(self.execute('a %d' %pin))
        except:
            return None
    
    def analog_write(self, pin, value):
        return self.execute_ack('x %d %d' %(pin, value))
    
    def digital_read(self, pin):
        try:
            return int(self.execute('d %d' %pin))
        except:
            return None
    
    def digital_write(self, pin, value):
        return self.execute_ack('w %d %d' %(pin, value))
    
    def digital_pin_mode(self, pin, mode):
        return self.execute_ack('c %d %d' %(pin, mode))
    
    def config_servo(self, pin, step_delay):
        ''' Configure a PWM servo '''
        return self.execute_ack('j %d %u' %(pin, step_delay))

    def servo_write(self, id, pos):
        ''' Usage: servo_write(id, pos)
            Position is given in degrees from 0-180
        '''
        return self.execute_ack('s %d %d' %(id, pos))
    
    def servo_read(self, id):
        ''' Usage: servo_read(id)
            The returned position is in degrees
        '''
        return int(self.execute('t %d' %id))
    
    def set_servo_delay(self, id, delay):
        ''' Usage: set_servo_delay(id, delay)
            Set the delay in ms inbetween servo position updates.  Controls speed of servo movement.
        '''
        return self.execute_ack('v %d %d' %(id, delay))

    def detach_servo(self, id):
        ''' Usage: detach_servo(id)
            Detach a servo from control by the Arduino
        '''        
        return self.execute_ack('z %d' %id)
    
    def attach_servo(self, id):
        ''' Usage: attach_servo(id)
            Attach a servo to the Arduino
        '''        
        return self.execute_ack('y %d' %id)
    
    def ping(self, pin):
        ''' The srf05/Ping command queries an SRF05/Ping sonar sensor
            connected to the General Purpose I/O line pinId for a distance,
            and returns the range in cm.  Sonar distance resolution is integer based.
        '''
        return self.execute('p %d' %pin);
    
#    def get_maxez1(self, triggerPin, outputPin):
#        ''' The maxez1 command queries a Maxbotix MaxSonar-EZ1 sonar
#            sensor connected to the General Purpose I/O lines, triggerPin, and
#            outputPin, for a distance, and returns it in Centimeters. NOTE: MAKE
#            SURE there's nothing directly in front of the MaxSonar-EZ1 upon
#            power up, otherwise it wont range correctly for object less than 6
#            inches away! The sensor reading defaults to use English units
#            (inches). The sensor distance resolution is integer based. Also, the
#            maxsonar trigger pin is RX, and the echo pin is PW.
#        '''
#        return self.execute('z %d %d' %(triggerPin, outputPin)) 
 

""" Basic test for connectivity """
if __name__ == "__main__":
    if os.name == "posix":
        portName = "/dev/ttyACM0"
    else:
        portName = "COM43" # Windows style COM port.
        
    baudRate = 57600

    myArduino = Arduino(port=portName, baudrate=baudRate, timeout=0.5)
    myArduino.connect()
     
    print "Sleeping for 1 second..."
    time.sleep(1)   
    
    print "Reading on analog port 0", myArduino.analog_read(0)
    print "Reading on digital port 0", myArduino.digital_read(0)
    print "Blinking the LED 3 times"
    for i in range(3):
        myArduino.digital_write(13, 1)
        time.sleep(1.0)
    #print "Current encoder counts", myArduino.encoders()
    
    print "Connection test successful.",
    
    myArduino.stop()
    myArduino.close()
    
    print "Shutting down Arduino."
    
