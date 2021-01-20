#!/usr/bin/env python
import time
import busio
import board
import numpy as np
from PIL import Image
import adafruit_amg88xx
import matplotlib.pyplot as plt

I2C_ADR = 0x68              # I2C アドレス

plt.ion()
plt.subplots(figsize=(8, 4))

# I2Cバスの初期化
i2c_bus = busio.I2C(board.SCL, board.SDA)
# センサの初期化
sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=I2C_ADR)
# センサの初期化待ち
time.sleep(.1)
# サーミスタ温度
thermistor_temp = round(sensor.temperature, 1)

try:
    while True:
        # 8x8センサアレイ内の最大温度を取得
        pixels_array = np.array(sensor.pixels)
        # サーミスタ温度補正
        offset_temp = round((0.8424 * thermistor_temp - 3.2523), 2)
        # 体温
        body_temp_array = pixels_array + offset_temp
        body_temp_max = round(np.amax(body_temp_array), 1)
 
        plt.subplot(1,2,1)
        plt.imshow(body_temp_array, cmap="inferno", interpolation="bicubic",vmin=30,vmax=40)
        plt.colorbar()
        plt.show
        plt.draw()
        plt.pause(0.01)
        plt.clf()
 
except KeyboardInterrupt:
    print("finish")