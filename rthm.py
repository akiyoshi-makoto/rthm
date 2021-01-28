#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from enum import Enum
import time
import datetime
import os
import RPi.GPIO as GPIO
import csv
import busio
import board
import adafruit_amg88xx
import cv2
import numpy as np
import PIL.Image, PIL.ImageTk


##############################################################################
# 定数
##############################################################################
I2C_ADR = 0x68                      # I2C アドレス
PROC_CYCLE = 30                     # 処理周期[msec]
TRIG = 27                           # 超音波センサ(HC-SR04)端子番号 TRIG
ECHO = 22                           # 超音波センサ(HC-SR04)端子番号 ECHO
DISTANCE_STANDARD = 60.0            # 体温測定対象者までの距離(基準値)
BODY_TEMP_STANDARD = 36.2           # 体温の基準値[℃]
LOG_PATH = './log_file/'            # ログファイル保存パス

# 周期処理状態
class CycleProcState(Enum):
    FACE_RECOGNITION = 0            # 顔認識処理
    DISTANCE_1 = 1                  # 体温測定対象者までの距離取得(1回目)
    THERMISTOR = 2                  # サーマルセンサ(AMG8833) サーミスタ 温度取得
    DISTANCE_2 = 3                  # 体温測定対象者までの距離取得(2回目)
    TEMPERATURE = 4                 # サーマルセンサ(AMG8833) 赤外線アレイセンサ 検出温度取得
    MAKE_BODY_TEMP = 5              # 体温演算
    UPDATE_CSV = 6                  # CSV更新処理
    PAUSE = 7                       # 一時停止処理
    ERROR = 8                       # エラー処理
    CLEAR_FRAME = 9                 # 停止画の空読み
    
##############################################################################
# クラス：Application
##############################################################################
class Application(ttk.Frame):
    def __init__(self, master=None):
        ttk.Frame.__init__(self, master)

        self.pack()
        # ウィンドウをスクリーンの中央に配置
        self.setting_window(master)

        # 周期処理状態
        self.cycle_proc_state = CycleProcState.FACE_RECOGNITION
        # 一時停止タイマ
        self.pause_timer = 0
        # 体温測定対象者までの距離
        self.distance = [DISTANCE_STANDARD, DISTANCE_STANDARD]
        # 距離補正
        self.corr_distance = 0.0 
        # サーミスタ温度
        self.thermistor_temp = 0.0
        # サーミスタ温度補正
        self.corr_thermistor = 0.0
        # 検出温度
        self.sensor_temp = BODY_TEMP_STANDARD
        # 体温
        self.body_temp = BODY_TEMP_STANDARD

        # ウィジットを生成
        self.create_widgets()
        # カメラ
        self.camera_init()
        # 超音波センサ(HC-SR04)
        ret_sonic_sensor = self.sonic_sensor_init()
        # サーマルセンサ(AMG8833)
        self.thermal_sensor_init()
        # CSV出力の初期設定
        self.csv_init()
        
        if not self.camera.isOpened:
            messagebox.showerror('カメラ認識エラー', 'カメラの接続を確認してください')
        elif not ret_sonic_sensor:
            messagebox.showerror('超音波センサエラー', '超音波センサの接続を確認してください')
        else:
            # 周期処理
            self.cycle_proc()

    ##########################################################################
    # ウィンドウをスクリーンの中央に配置
    ##########################################################################
    def setting_window(self, master):
        w = 500                             # ウィンドウの横幅
        h = 800                             # ウィンドウの高さ
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
        frame_upper.grid(row=0, padx=10, pady=(10,0), sticky='NW')
        self.label_msg = ttk.Label(frame_upper, font=('',20))
        self.label_msg.grid(row=0, sticky='NW')
        self.label_body_tmp = ttk.Label(frame_upper, font=('',30))
        self.label_body_tmp.grid(row=1, sticky='NW')
        # フレーム(中央部)
        frame_middle = ttk.Frame(self)
        frame_middle.grid(row=1, padx=10, pady=(10,0), sticky='NW')
        # カメラの映像を表示するキャンバスを用意する
        self.canvas_camera = Canvas(frame_middle, width=480, height=480)
        self.canvas_camera.pack()

        # フレーム(下部)
        frame_lower = ttk.Frame(self)
        frame_lower.grid(row=2, padx=10, pady=(10,0), sticky='NW')
        
        self.label_distance1 = ttk.Label(frame_lower)
        self.label_distance1.grid(row=0, sticky='NW')
        self.label_distance2 = ttk.Label(frame_lower)
        self.label_distance2.grid(row=1, sticky='NW')
        self.label_corr_distance = ttk.Label(frame_lower)
        self.label_corr_distance.grid(row=2, sticky='NW')
        self.label_thermistor = ttk.Label(frame_lower)
        self.label_thermistor.grid(row=3, sticky='NW')
        self.label_corr_thermistor = ttk.Label(frame_lower)
        self.label_corr_thermistor.grid(row=4, sticky='NW')
        self.label_sns_tmp = ttk.Label(frame_lower)
        self.label_sns_tmp.grid(row=5, sticky='NW')

        self.init_param_widgets()

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):        
        # フレーム(上部)
        self.label_msg.config(text='顔が青枠に合うよう近づいてください')
        self.label_body_tmp.config(text='体温：--.-- ℃')
        # フレーム(下部)
        self.label_distance1.config(text='距離(1回目)：--- cm')
        self.label_distance2.config(text='距離(2回目)：--- cm')
        self.label_corr_distance.config(text='距離補正：--.-- ℃')
        self.label_thermistor.config(text='サーミスタ温度：--.-- ℃')
        self.label_corr_thermistor.config(text='サーミスタ温度補正：--.-- ℃')
        self.label_sns_tmp.config(text='検出温度：--.-- ℃')

    ##########################################################################
    # カメラ　初期化
    ##########################################################################
    def camera_init(self):   
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # print(self.camera.get(cv2.CAP_PROP_FPS))

        # 顔検出のための学習元データを読み込む
        self.face_cascade = cv2.CascadeClassifier('haarcascades/haarcascade_frontalface_default.xml')

    ##########################################################################
    # 停止画取得
    ##########################################################################
    def camera_get_frame(self):
        # 停止画を取得
        ret, frame = self.camera.read()
    
    ##########################################################################
    # 顔認識処理
    ##########################################################################
    def face_recognition(self):
        # 停止画を取得
        ret, frame = self.camera.read()
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
                                                      minSize=(150, 150))
        # 検出した場所すべてに緑色で枠を描画する
        for rect in facerect:
            cv2.rectangle(frame_color,
                            tuple(rect[0:2]),
                            tuple(rect[0:2]+rect[2:4]),
                            (0, 255, 0),
                            thickness=3)

        # ガイド枠の描画
        cv2.rectangle(frame_color, (60,60), (420,420), (0,0,255), thickness=3)
        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas_camera.create_image(0, 0, image = self.photo, anchor = 'nw')

        return len(facerect)

    ##########################################################################
    # 超音波センサ(HC-SR04) 初期化
    ##########################################################################
    def sonic_sensor_init(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(TRIG, GPIO.OUT)
        GPIO.setup(ECHO, GPIO.IN)
        GPIO.output(TRIG, GPIO.LOW)

        # Trig端子を10us以上High
        GPIO.output(TRIG, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(TRIG, GPIO.LOW)
        
        time1 = time.time()
        result = True
        # EchoパルスがHighになる時間
        while GPIO.input(ECHO) == 0:
            time2 = time.time()
            time_chk = time2 - time1
            if time_chk > 0.001:
                result = False
                break
        return result

    ##########################################################################
    # 超音波センサ(HC-SR04) 距離取得
    ##########################################################################
    def sonic_sensor_ctrl(self):
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
        # print(echo_pulse_width)
        # 距離を算出:Distance in cm = echo pulse width in uS/58
        distance = round((echo_pulse_width / 58), 1)

        return distance

    ##########################################################################
    # サーマルセンサ(AMG8833) 初期化
    ##########################################################################
    def thermal_sensor_init(self):   
        # I2Cバスの初期化
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        # センサの初期化
        self.sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=I2C_ADR)
        # センサの初期化待ち
        time.sleep(.1)

    ##########################################################################
    # 体温演算
    ##########################################################################
    def make_body_temp(self):
        self.label_distance1.config(text='距離(1回目)：' + str(self.distance[0]) + ' cm ')
        self.label_distance2.config(text='距離(2回目)：' + str(self.distance[1]) + ' cm ')
        self.label_thermistor.config(text='サーミスタ温度：' + str(self.thermistor_temp) + ' ℃')
        self.label_sns_tmp.config(text='検出温度：' + str(self.sensor_temp) + '℃')

        if (self.distance[0] < DISTANCE_STANDARD and
            self.distance[1] < DISTANCE_STANDARD):

            if (self.distance[0] < 30.0 or
                self.distance[1] < 30.0):
                self.label_msg.config(text='もう少し離れてください')
                result = False
            else:
                # 距離(平均)
                distance_ave = round(((self.distance[0] + self.distance[1]) / 2), 1)
                # 距離補正
                self.corr_distance = round(((DISTANCE_STANDARD - distance_ave) * 0.064), 2)
                # サーミスタ温度補正
                self.corr_thermistor = round((0.8424 * self.thermistor_temp - 3.2523), 2)
                # 体温
                self.body_temp = round((self.sensor_temp - self.corr_distance + self.corr_thermistor), 1)

                self.label_corr_distance.config(text='距離補正：' + str(self.corr_distance) + ' ℃')
                self.label_corr_thermistor.config(text='サーミスタ温度補正：' + str(self.corr_thermistor) + ' ℃')
                self.label_body_tmp.config(text='体温：' + str(self.body_temp) + '℃')
                
                if self.body_temp > 38.0:
                    self.label_msg.config(text='体温が高いです！検温してください')
                else:
                    self.label_msg.config(text='体温は正常です！問題ありません')

                result = True
        else:
            self.label_msg.config(text='もう少し近づいてください') 
            result = False
        
        return result

    ##########################################################################
    # CSV出力の初期設定
    ##########################################################################
    def csv_init(self):
        # フォルダの存在チェック
        if not os.path.isdir(LOG_PATH):
            os.makedirs(LOG_PATH)
        # 現在時刻取得
        now = datetime.datetime.today()     
        now_str = now.strftime('%y%m%d-%H%M%S')
        # csvファイルの生成
        self.filename = LOG_PATH + now_str + '.csv'
        with open(self.filename, 'a', newline='') as csvfile:
            file = csv.writer(csvfile)
            # 1行目：見出し
            file.writerow(['距離(1回目)',
                           '距離(2回目)',
                           '距離補正',
                           'サーミスタ温度',
                           'サーミスタ温度補正',
                           '検出温度',
                           '体温'])

    ##########################################################################
    # CSV出力
    ##########################################################################
    def csv_ctrl(self):
        # csvファイルの生成
        with open(self.filename, 'a', newline='') as csvfile:
            file = csv.writer(csvfile)
            # csvファイルへの書き込みデータ
            data = [self.distance[0],
                    self.distance[1],
                    self.corr_distance,
                    self.thermistor_temp,
                    self.corr_thermistor,
                    self.sensor_temp,
                    self.body_temp]
            # データの書き込み
            file.writerow(data)

    ##########################################################################
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        # 顔認識待ち
        if self.cycle_proc_state == CycleProcState.FACE_RECOGNITION:
            # 顔認識処理
            facerect_num = self.face_recognition()
            # 認識した顔が一つの場合
            if facerect_num == 1:
                self.cycle_proc_state = CycleProcState.DISTANCE_1
                self.label_msg.config(text='')
            # 認識した顔が複数の場合
            elif facerect_num > 1:
                self.pause_timer = 0
                self.cycle_proc_state = CycleProcState.ERROR
                self.label_msg.config(text='体温計測は一人ずつです')
            # 顔認識をしなかった場合
            else:
                self.cycle_proc_state = CycleProcState.FACE_RECOGNITION

        # 体温測定対象者までの距離計測(1回目)
        elif self.cycle_proc_state == CycleProcState.DISTANCE_1:            
            self.distance[0] = self.sonic_sensor_ctrl()
            self.cycle_proc_state = CycleProcState.THERMISTOR

        # サーマルセンサ(AMG8833) サーミスタ 温度取得
        elif self.cycle_proc_state == CycleProcState.THERMISTOR:
            self.thermistor_temp = round(self.sensor.temperature, 2) 
            self.cycle_proc_state = CycleProcState.DISTANCE_2
 
        # 体温測定対象者までの距離計測(2回目)
        elif self.cycle_proc_state == CycleProcState.DISTANCE_2:            
            self.distance[1] = self.sonic_sensor_ctrl()
            self.cycle_proc_state = CycleProcState.TEMPERATURE

        # サーマルセンサ(AMG8833) 赤外線アレイセンサ 検出温度取得
        elif self.cycle_proc_state == CycleProcState.TEMPERATURE:
            self.sensor_temp = round(np.amax(np.array(self.sensor.pixels)), 2)
            self.cycle_proc_state = CycleProcState.MAKE_BODY_TEMP

        # 体温演算
        elif self.cycle_proc_state == CycleProcState.MAKE_BODY_TEMP:
            result = self.make_body_temp()
            if result:
                self.cycle_proc_state = CycleProcState.UPDATE_CSV
            else:
                self.pause_timer = 0
                self.cycle_proc_state = CycleProcState.ERROR
   
        # CSV更新処理
        elif self.cycle_proc_state == CycleProcState.UPDATE_CSV:
            self.csv_ctrl()
            self.pause_timer = 0
            self.cycle_proc_state = CycleProcState.PAUSE

        # 一時停止処理
        elif self.cycle_proc_state == CycleProcState.PAUSE:
            self.pause_timer += 1
            if self.pause_timer > 100:
                self.pause_timer = 0
                self.cycle_proc_state = CycleProcState.CLEAR_FRAME

        # エラー処理
        elif self.cycle_proc_state == CycleProcState.ERROR:
            self.pause_timer += 1
            if self.pause_timer > 50:
                self.pause_timer = 0
                self.cycle_proc_state = CycleProcState.CLEAR_FRAME
        
        # 停止画の空読み
        elif self.cycle_proc_state == CycleProcState.CLEAR_FRAME:
            # 停止画取得
            self.camera_get_frame()
            self.pause_timer += 1
            if self.pause_timer > 10:
                self.cycle_proc_state = CycleProcState.FACE_RECOGNITION
                # 計測データ ウィジット 初期化
                self.init_param_widgets()

        # 設計上ありえないがロバスト性に配慮
        else:
            print('[error] cycle_proc')
            self.cycle_proc_state = CycleProcState.FACE_RECOGNITION

        # 周期処理
        self.after(PROC_CYCLE, self.cycle_proc)

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    app.mainloop()
    # 終了処理
    GPIO.cleanup()