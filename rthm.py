#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
import time
import RPi.GPIO as GPIO
import busio
import board
import adafruit_amg88xx
import cv2
import numpy as np
import PIL.Image, PIL.ImageTk

##############################################################################
# 定数
##############################################################################
TRIG = 27
ECHO = 22
CYCLE_TIME = 50             # 処理周期[msec]
I2C_ADR = 0x68              # I2C アドレス
FACE_DETECTIION_PAUSE = 40  # 顔検出時の一時停止周期
TARGET_DISTANCE = 60.0      # 対象までの距離(基準値)

############################################################
# オプション設定    True:有効 False:無効
############################################################
# 超音波センサ(HC-SR04)
ENABLE_ULTRA_SONIC_SENSOR = True   

class Application(ttk.Frame):
    def __init__(self, master=None):
        ttk.Frame.__init__(self, master)
        self.master = master
        self.pack()
        # ウィンドウをスクリーンの中央に配置
        self.setting_window(master)

        self.cycle_proc_exec = True     # 周期処理実行許可フラグ(True:許可 False:禁止)
        self.pause_timer = 0            # 顔検出時の一時停止タイマ 
        self.face_detection = False     # 顔検出フラグ(True:検出した False:検出していない)
        self.distance = TARGET_DISTANCE

        # ウィジットを生成
        self.create_widgets()
        # デバイスの初期化
        self.init_device()
        # 周期処理
        self.cycle_proc()

    ##########################################################################
    # ウィンドウをスクリーンの中央に配置
    ##########################################################################
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
    
    ##########################################################################
    # ウィジットを生成
    ##########################################################################
    def create_widgets(self):
        # フレーム(上部)
        frame_upper = ttk.Frame(self)
        frame_upper.grid(row=0, padx=10, pady=10, sticky='NW')
        # ビデオカメラの映像を表示するキャンバスを用意する
        self.canvas_video = Canvas(frame_upper, width=480, height=480)
        self.canvas_video.pack()

        # フレーム(下部)
        frame_lower = ttk.Frame(self)
        frame_lower.grid(row=1, padx=10, pady=10, sticky='NW')
        
        self.label_tgt_tmp = ttk.Label(frame_lower)
        self.label_tgt_tmp.grid(row=0, sticky='NW')
        self.label_env_tmp = ttk.Label(frame_lower)
        self.label_env_tmp.grid(row=2, sticky='NW')
        self.label_offset_tmp = ttk.Label(frame_lower)
        self.label_offset_tmp.grid(row=5, sticky='NW')
        
        if ENABLE_ULTRA_SONIC_SENSOR:
            self.label_distance = ttk.Label(frame_lower)
            self.label_distance.grid(row=4, sticky='NW')

        self.init_param_widgets()

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):
        self.label_tgt_tmp.config(text='体温：--.- ℃')
        self.label_env_tmp.config(text='サーミスタ温度：--.- ℃')
        self.label_offset_tmp.config(text='オフセット値：--.- ℃')

        if ENABLE_ULTRA_SONIC_SENSOR:
            self.label_distance.config(text='対象物までの距離：--- cm')
    
    ##########################################################################
    # デバイスの初期化
    ##########################################################################
    def init_device(self):   
        # ビデオカメラ
        self.init_video_camera()
        # 超音波センサ(HC-SR04)
        if ENABLE_ULTRA_SONIC_SENSOR:
            self.init_ultra_sonic_sensor()
        # サーマルカメラ(AMG8833)
        self.init_thermal_camera()

    ##########################################################################
    # ビデオカメラ　初期化
    ##########################################################################
    def init_video_camera(self):   
        self.video_camera = cv2.VideoCapture(0)
        self.video_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.video_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # 顔検出のための学習元データを読み込む
        self.face_cascade = cv2.CascadeClassifier('haarcascades/haarcascade_frontalface_default.xml')

    ##########################################################################
    # ビデオカメラ 制御
    ##########################################################################
    def ctrl_video_camera(self):
        if self.video_camera.isOpened():

            # ビデオカメラの停止画を取得
            ret, frame = self.video_camera.read()

            if self.pause_timer > 0:
                self.pause_timer -= 1
            else:
                # 左右反転
                frame_mirror = cv2.flip(frame, 1)
                # OpenCV(BGR) -> Pillow(RGB)変換
                frame_color = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)
                # 顔検出の処理効率化のために、写真の情報量を落とす（モノクロにする）
                frame_gray = cv2.cvtColor(frame_color, cv2.COLOR_BGR2GRAY)
                # 顔検出を行う(detectMultiScaleの戻り値は(x座標, y座標, 横幅, 縦幅)のリスト)
                facerect = self.face_cascade.detectMultiScale(frame_gray,
                                                              scaleFactor=1.2,
                                                              minNeighbors=2,
                                                              minSize=(320, 320))
                # 顔が検出された場合
                if len(facerect) > 0:
                    # 一時停止してその間にサーマルカメラ制御を実行する
                    self.pause_timer = FACE_DETECTIION_PAUSE
                    # 顔検出フラグセット
                    self.face_detection = True
                    # 検出した場所すべてに緑色で枠を描画する
                    for rect in facerect:
                        cv2.rectangle(frame_color,
                                      tuple(rect[0:2]),
                                      tuple(rect[0:2]+rect[2:4]),
                                      (0, 255, 0),
                                      thickness=3)

                else:
                    self.pause_timer = 0
                    self.init_param_widgets()

                # OpenCV frame -> Pillow Photo
                self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
                # Pillow Photo -> Canvas
                self.canvas_video.create_image(0, 0, image = self.photo, anchor = 'nw')

    ##########################################################################
    # 超音波センサ(HC-SR04) 初期化
    ##########################################################################
    def init_ultra_sonic_sensor(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(TRIG, GPIO.OUT)
        GPIO.setup(ECHO, GPIO.IN)
        GPIO.output(TRIG, GPIO.LOW)

    ##########################################################################
    # 超音波センサ(HC-SR04) 制御
    ##########################################################################
    def ctrl_ultra_sonic_sensor(self):

        if self.face_detection: 
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
            self.label_distance.config(text='対象物までの距離：' + str(round(self.distance)) + ' cm' )

    ##########################################################################
    # サーマルカメラ(AMG8833) 初期化
    ##########################################################################
    def init_thermal_camera(self):   
        # I2Cバスの初期化
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        # センサの初期化
        self.sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=I2C_ADR)
        # センサの初期化待ち
        time.sleep(.1)
        
    ##########################################################################
    # サーマルカメラ(AMG8833) 制御
    ##########################################################################
    def ctrl_thermal_camera(self):
        
        if self.face_detection: 
            # 顔検出フラグをクリア
            self.face_detection = False
            # サーミスタ温度
            thermistor_temp = self.sensor.temperature
            # 検出温度
            pixels_array = np.array(self.sensor.pixels)
            # サーミスタ温度補正
            offset_temp = (-0.6857 * thermistor_temp + 25.5)
            # 距離補正
            if self.distance <= TARGET_DISTANCE:
                offset_temp = offset_temp - ((TARGET_DISTANCE - self.distance) * 0.064)
            offset_temp = round(offset_temp, 1)
            # 体温
            body_temp_array = pixels_array + offset_temp
            body_temp_max = round(np.amax(body_temp_array), 1)

            self.label_tgt_tmp.config(text='体温：' + str(body_temp_max) + ' ℃')
            self.label_env_tmp.config(text='サーミスタ温度：' + str(thermistor_temp) + ' ℃')
            self.label_offset_tmp.config(text='オフセット値：' + str(offset_temp) + ' ℃')
            
            # print(body_temp_array)

    ##########################################################################
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        # 周期処理実行許可
        if self.cycle_proc_exec:
            # ビデオカメラ
            self.ctrl_video_camera()
            # 超音波センサ(HC-SR04)
            if ENABLE_ULTRA_SONIC_SENSOR:
                self.ctrl_ultra_sonic_sensor()
            # サーマルカメラ(AMG8833)
            self.ctrl_thermal_camera()
            # 周期処理
            self.after(CYCLE_TIME, self.cycle_proc)

    ##########################################################################
    # 閉じるボタンが押下された場合の処理
    ##########################################################################
    def on_close_button(self):
        # 周期処理実行禁止
        self.cycle_proc_exec = False
        # 終了処理
        self.video_camera.release()
        if ENABLE_ULTRA_SONIC_SENSOR:
            GPIO.cleanup()
        # メインウインドウを閉じる
        self.master.destroy()

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    root.protocol('WM_DELETE_WINDOW', app.on_close_button)
    app.mainloop()