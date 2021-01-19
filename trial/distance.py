#!/usr/bin/env python
import time
import RPi.GPIO as GPIO
 
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
TRIG = 27
ECHO = 22
 
# GPIO端子の初期設定
GPIO.setup(TRIG,GPIO.OUT)
GPIO.setup(ECHO,GPIO.IN)
GPIO.output(TRIG, GPIO.LOW)
time.sleep(0.3)
 
# Trig端子を10us以上High
GPIO.output(TRIG, GPIO.HIGH)
time.sleep(0.00001)
GPIO.output(TRIG, GPIO.LOW)
 
# EchoパルスがHighになる時間
while GPIO.input(ECHO) == 0:
    echo_on = time.time()
 
# EchoパルスがLowになる時間
while GPIO.input(ECHO) == 1:
    echo_off = time.time()
 
# Echoパルスのパルス幅(us)
echo_pulse_width = (echo_off - echo_on) * 1000000
 
# 距離を算出:Distance in cm = echo pulse width in uS/58
distance = echo_pulse_width / 58
 
print(distance)