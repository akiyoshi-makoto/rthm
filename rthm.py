#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
import time
import RPi.GPIO as GPIO
import busio
import board
from smbus2 import SMBus
import adafruit_amg88xx
import cv2
import numpy as np
import PIL.Image, PIL.ImageTk

############################################################
# 定数
############################################################
TRIG = 27
ECHO = 22
CYCLE_TIME = 100        # 処理周期[msec]
DISTANCE_DEFAULT = 50   # 対象物までの距離(デフォルト値)
I2C_ADR = 0x68          # I2C アドレス

############################################################
# オプション設定
############################################################
# 超音波センサ(HC-SR04)
ENABLE_ULTRA_SONIC_SENSOR = False   # True:有効 False:無効
# サーマルカメラ(AMG8833)
ENABLE_THERMAL_CAMERA = False       # True:有効 False:無効     
# 顔検出制御
ENABLE_FACE_DETECTIION = False      # True:有効 False:無効

class Application(ttk.Frame):
    def __init__(self, master=None):
        ttk.Frame.__init__(self, master)
        self.master = master
        self.pack()
        # ウィンドウをスクリーンの中央に配置
        self.setting_window(master)
        # ウィジットを生成
        self.create_widgets()
        # デバイスの初期化
        self.init_device()
        # 周期処理
        self.cycle_proc_exec = True
        self.cycle_proc()

    ############################################################
    # ウィンドウをスクリーンの中央に配置
    ############################################################
    def setting_window(self, master):
        w = 500                             # ウィンドウの横幅
        h = 700                             # ウィンドウの高さ
        sw = master.winfo_screenwidth()     # スクリーンの横幅
        sh = master.winfo_screenheight()    # スクリーンの高さ
        # ウィンドウをスクリーンの中央に配置
        master.geometry(str(w)+'x'+str(h)+'+'+str(int(sw/2-w/2))+'+'+str(int(sh/2-h/2)))
        # ウィンドウの最小サイズを指定
        master.minsize(w,h)
        master.title('体温測定システム')
    
    ############################################################
    # ウィジットを生成
    ############################################################
    def create_widgets(self):
        # フレーム(カメラ)
        frame_camera = ttk.Frame(self)
        frame_camera.grid(row=0, padx=10, pady=(10,0), sticky='NW')
        # ビデオカメラの映像を表示するキャンバスを用意する
        self.canvas = Canvas(frame_camera, width=480, height=480)
        self.canvas.pack()

        # フレーム(測定データ)
        frame_data = ttk.Frame(self)
        frame_data.grid(row=1, padx=10, pady=(10,0), sticky='NW')

        # サーマルカメラ(AMG8833)
        if ENABLE_THERMAL_CAMERA:
            self.label_tgt_tmp = ttk.Label(frame_data, text='体温：')
            self.label_tgt_tmp.grid(row=0, sticky='NW')

            self.label_env_tmp = ttk.Label(frame_data, text='サーミスタ温度：')
            self.label_env_tmp.grid(row=2, sticky='NW')

            self.label_max_tmp = ttk.Label(frame_data, text='最大温度：')
            self.label_max_tmp.grid(row=3, sticky='NW')

            self.label_offset_tmp = ttk.Label(frame_data, text='オフセット値：')
            self.label_offset_tmp.grid(row=5, sticky='NW')

        # 超音波センサ(HC-SR04)
        if ENABLE_ULTRA_SONIC_SENSOR:
            self.label_distance = ttk.Label(frame_data, text='対象物までの距離：')
            self.label_distance.grid(row=4, sticky='NW')

    ############################################################
    # デバイスの初期化
    ############################################################
    def init_device(self):   
        # 超音波センサ(HC-SR04)
        if ENABLE_ULTRA_SONIC_SENSOR:
            self.init_ultra_sonic_sensor()
        else:
            self.distance = DISTANCE_DEFAULT    # 対象物までの距離
        # サーマルカメラ(AMG8833)
        if ENABLE_THERMAL_CAMERA:
            self.init_thermal_camera()
        # ビデオカメラ
        self.init_video_camera()

    ############################################################
    # 周期処理
    ############################################################
    def cycle_proc(self):
        # 周期処理実行許可
        if self.cycle_proc_exec:
            # 超音波センサ(HC-SR04)
            if ENABLE_ULTRA_SONIC_SENSOR:
                self.ctrl_ultra_sonic_sensor()
            # サーマルカメラ(AMG8833)
            if ENABLE_THERMAL_CAMERA:
                self.ctrl_thermal_camera()
            # ビデオカメラ
            self.ctrl_video_camera()
            # 周期処理
            self.after(CYCLE_TIME, self.cycle_proc)

    ############################################################
    # 閉じるボタンが押下された場合の処理
    ############################################################
    def on_close_button(self):
        # 周期処理実行禁止
        self.cycle_proc_exec = False
        # 終了処理
        GPIO.cleanup()
        self.video_camera.release()
        # メインウインドウを閉じる
        self.master.destroy()

    ############################################################
    # 超音波センサ(HC-SR04) 初期化
    ############################################################
    def init_ultra_sonic_sensor(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(TRIG, GPIO.OUT)
        GPIO.setup(ECHO, GPIO.IN)
        GPIO.output(TRIG, GPIO.LOW)

    ############################################################
    # 超音波センサ(HC-SR04) 制御
    ############################################################
    def ctrl_ultra_sonic_sensor(self):
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
        self.distance = echo_pulse_width / 58

        self.label_distance.config(text='対象物までの距離：' + str(round(self.distance)))

    ############################################################
    # サーマルカメラ(AMG8833) 初期化
    ############################################################
    def init_thermal_camera(self):   
        # I2Cバスの初期化
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        # センサの初期化
        self.sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=I2C_ADR)
        # センサの初期化待ち
        time.sleep(.1)

        with SMBus(1) as i2c:
            # AMG8833追加設定
            # フレームレート(0x00:10fps, 0x01:1fps)
            i2c.write_byte_data(I2C_ADR, 0x02, 0x00)
            # INT出力無効
            i2c.write_byte_data(I2C_ADR, 0x03, 0x00)
            # 移動平均モードを有効
            i2c.write_byte_data(I2C_ADR, 0x1F, 0x50)
            i2c.write_byte_data(I2C_ADR, 0x1F, 0x45)
            i2c.write_byte_data(I2C_ADR, 0x1F, 0x57)
            i2c.write_byte_data(I2C_ADR, 0x07, 0x20)
            i2c.write_byte_data(I2C_ADR, 0x1F, 0x00)
            # 移動平均モードを無効
            #i2c.write_byte_data(I2C_ADR, 0x1F, 0x50)
            #i2c.write_byte_data(I2C_ADR, 0x1F, 0x45)
            #i2c.write_byte_data(I2C_ADR, 0x1F, 0x57)
            #i2c.write_byte_data(I2C_ADR, 0x07, 0x00)
            #i2c.write_byte_data(I2C_ADR, 0x1F, 0x00)

    ############################################################
    # サーマルカメラ(AMG8833) 制御
    ############################################################
    def ctrl_thermal_camera(self):
        pixels_array = np.array(self.sensor.pixels)
        pixels_ave = np.average(pixels_array)
        pixels_max = np.amax(pixels_array[1:6,2:6])   
        pixels_min = np.amin(pixels_array)
        with SMBus(1) as i2c:
            thermistor_temp = i2c.read_word_data(I2C_ADR, 0xE)
        thermistor_temp = thermistor_temp * 0.0625
        offset_thrm = (-0.6857*thermistor_temp+27.187)  # 補正式

        if self.distance <= 60:
            offset_thrm = offset_thrm-((60-self.distance)*0.064)    # 補正式(対距離)
         
        offset_temp = offset_thrm
        max_temp = round(pixels_max + offset_temp, 1)   #体温を算出

        self.label_tgt_tmp.config(text='体温：' + str(max_temp) + ' ℃')
        self.label_env_tmp.config(text='サーミスタ温度：' + str(thermistor_temp) + ' ℃')
        self.label_max_tmp.config(text='最大温度：' + str(pixels_max) + ' ℃')
        self.label_offset_tmp.config(text='オフセット値：' + str(offset_temp) + ' ℃')
        
        print(pixels_array)

    ############################################################
    # ビデオカメラ　初期化
    ############################################################
    def init_video_camera(self):   
        self.video_camera = cv2.VideoCapture(0)
        self.video_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.video_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ############################################################
    # ビデオカメラ 制御
    ############################################################
    def ctrl_video_camera(self):
        # ビデオカメラの停止画を取得
        _, frame = self.video_camera.read()
        frame_color = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 顔検出制御
        if ENABLE_FACE_DETECTIION:
            # 顔検出の処理効率化のために、写真の情報量を落とす（モノクロにする）
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 顔検出のための学習元データを読み込む
            face_cascade = cv2.CascadeClassifier('haarcascades/haarcascade_frontalface_default.xml')
            # 顔検出を行う
            facerect = face_cascade.detectMultiScale(frame_gray, scaleFactor=1.2, minNeighbors=2, minSize=(100, 100))
            # 顔が検出された場合
            if len(facerect) > 0:
                # 検出した場所すべてに青色で枠を描画する
                for rect in facerect:
                    cv2.rectangle(frame_color, tuple(rect[0:2]), tuple(rect[0:2]+rect[2:4]), (0, 0, 255), thickness=3)

        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas.create_image(0, 0, image = self.photo, anchor = 'nw')

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    root.protocol('WM_DELETE_WINDOW', app.on_close_button)
    app.mainloop()