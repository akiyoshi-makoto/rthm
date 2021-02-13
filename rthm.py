#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from enum import Enum
import time
import datetime
import os
import csv
import cv2
import numpy as np
import PIL.Image, PIL.ImageTk
import busio
import board
import adafruit_amg88xx
import VL53L0X 

##############################################################################
# 定数
##############################################################################
PROC_CYCLE = 50                     # 処理周期[msec]
DISTANCE_STANDARD = 50.0            # 距離(基準値)[cm]
DISTANCE_UPPER_LIMIT = 100.0        # 距離(上限値)[cm]
DISTANCE_LOWER_LIMIT = 30.0         # 距離(下限値)[cm]
THERMISTOR_CORR_STANDARD = 10.0     # サーミスタ温度補正(基準値)[℃]
BODY_TEMP_STANDARD = 36.2           # 体温(基準値)[℃]
TARGET_DIFF = 0.5                   # 学習目標との差分[℃]
LOG_PATH = './log_file/'            # ログファイル保存パス

# 周期処理状態
class CycleProcState(Enum):
    FACE_DETECTION = 0              # 顔検出
    THERMISTOR = 1                  # サーミスタ温度
    TEMPERATURE = 2                 # 赤外線センサ温度
    DUMMY = 3                       # ダミー
    MAKE_BODY_TEMP = 4              # 体温演算
    UPDATE_CSV = 5                  # CSV更新
    PAUSE = 6                       # 一時停止

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
        self.cycle_proc_state = CycleProcState.FACE_DETECTION
        # 距離計測タイマ
        self.distance_timer = 0
        # 一時停止タイマ
        self.pause_timer = 0
        # 距離
        self.distance = DISTANCE_STANDARD
        # サーミスタ温度
        self.thermistor_temp = 0.0
        # サーミスタ温度補正
        self.thermistor_corr = THERMISTOR_CORR_STANDARD
        # 赤外線センサ温度(インデックス)
        self.temperature_index = 0
        # 赤外線センサ温度
        self.temperature = [0.0, 0.0, 0.0]
        # 赤外線センサ温度(中央値)
        self.temperature_med = 0.0
        # 体温
        self.body_temp = BODY_TEMP_STANDARD

        # ウィジットを生成
        self.create_widgets()
        # カメラ
        self.camera_init()
        # 距離センサ(VL530X)
        self.distance_sensor_init()
        # サーマルセンサ(AMG8833)
        self.thermal_sensor_init()
        # CSV出力の初期設定
        self.csv_init()
        
        if not self.camera.isOpened:
            messagebox.showerror('カメラ認識エラー', 'カメラの接続を確認してください')
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
        master.title('非接触体温計')
    
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

        self.label_distance = ttk.Label(frame_lower)
        self.label_distance.grid(row=0, sticky='NW')
        self.label_thermistor = ttk.Label(frame_lower)
        self.label_thermistor.grid(row=1, sticky='NW')
        self.label_thermistor_corr = ttk.Label(frame_lower)
        self.label_thermistor_corr.grid(row=2, sticky='NW')
        self.label_temperature_0 = ttk.Label(frame_lower)
        self.label_temperature_0.grid(row=3, sticky='NW')
        self.label_temperature_1 = ttk.Label(frame_lower)
        self.label_temperature_1.grid(row=4, sticky='NW')
        self.label_temperature_2 = ttk.Label(frame_lower)
        self.label_temperature_2.grid(row=5, sticky='NW')
        self.label_temperature_med = ttk.Label(frame_lower)
        self.label_temperature_med.grid(row=6, sticky='NW')

        self.init_param_widgets()

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):        
        # フレーム(上部)
        self.label_msg.config(text='顔が白枠に合うよう近づいてください')
        self.label_body_tmp.config(text='体温：--.-- ℃')
        # フレーム(下部)
        self.label_distance.config(text='距離：--- cm')
        self.label_thermistor.config(text='サーミスタ温度：--.-- ℃')
        self.label_thermistor_corr.config(text='サーミスタ温度補正：--.-- ℃')
        self.label_temperature_0.config(text='センサ温度(1回目)：--.-- ℃')
        self.label_temperature_1.config(text='センサ温度(2回目)：--.-- ℃')
        self.label_temperature_2.config(text='センサ温度(3回目)：--.-- ℃')
        self.label_temperature_med.config(text='センサ温度(中央値)：--.-- ℃')

    ##########################################################################
    # カメラ初期化
    ##########################################################################
    def camera_init(self):   
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # print(self.camera.get(cv2.CAP_PROP_FPS))

    ##########################################################################
    # カメラ制御
    ##########################################################################
    def camera_ctrl(self):
        ret, frame = self.camera.read()
        # 左右反転
        frame_mirror = cv2.flip(frame, 1)
        # OpenCV(BGR) -> Pillow(RGB)変換
        frame_color = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)
        # ガイド枠の描画
        cv2.rectangle(frame_color, (60,60), (420,420), (255,255,255), thickness=5)
        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas_camera.create_image(0, 0, image = self.photo, anchor = 'nw')

    ##########################################################################
    # カメラ映像の空読み
    ##########################################################################
    def camera_clear_frame(self):
        ret, frame = self.camera.read()

    ##########################################################################
    # 距離センサ(VL530X) 初期化
    ##########################################################################
    def distance_sensor_init(self):
        self.distance_sensor = VL53L0X.VL53L0X(address=0x29)
        self.distance_sensor.start_ranging(VL53L0X.VL53L0X_BETTER_ACCURACY_MODE)

    ##########################################################################
    # サーマルセンサ(AMG8833) 初期化
    ##########################################################################
    def thermal_sensor_init(self):   
        # I2Cバスの初期化
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        # センサの初期化
        self.thermal_sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=0x68)
 
    ##########################################################################
    # CSV出力の初期設定
    ##########################################################################
    def csv_init(self):
        # フォルダの存在チェック
        if not os.path.isdir(LOG_PATH):
            os.makedirs(LOG_PATH)
        # 日付取得
        now = datetime.datetime.today()
        # csvファイルの生成
        self.filename = LOG_PATH + now.strftime('%Y-%m') + '.csv'
        # ファイルの存在チェック
        if not os.path.isfile(self.filename):
            with open(self.filename, 'w', newline='') as csvfile:
                file = csv.writer(csvfile)
                # 1行目：見出し
                file.writerow(['日時',
                               '体温',
                               'センサ温度',
                               '距離',
                               'サーミスタ',
                               'サーミスタ補正'])

    ##########################################################################
    # CSV出力
    ##########################################################################
    def csv_ctrl(self):
        with open(self.filename, 'a', newline='') as csvfile:
            # csvファイルへの書き込みデータ
            now = datetime.datetime.today()
            data = [now.strftime('%Y-%m-%d %H:%M:%S'),
                    self.body_temp,
                    self.temperature_med,
                    self.distance,
                    self.thermistor_temp,
                    self.thermistor_corr]
            # データの書き込み
            file = csv.writer(csvfile)
            file.writerow(data)

    ##########################################################################
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        # 顔検出
        if self.cycle_proc_state == CycleProcState.FACE_DETECTION:
            # カメラ制御
            self.camera_ctrl()
            # 距離計測
            self.distance_timer += 1
            if self.distance_timer >= 10:
                self.distance_timer = 0
                self.distance = self.distance_sensor.get_distance() / float(10)

                if self.distance > DISTANCE_UPPER_LIMIT:
                    self.label_msg.config(text='顔が白枠に合うよう近づいてください')
                    self.label_distance.config(text='距離：--- cm')
                else:
                    if self.distance < DISTANCE_LOWER_LIMIT:
                        self.label_msg.config(text='もう少し離れてください')
                    elif self.distance > DISTANCE_STANDARD:
                        self.label_msg.config(text='もう少し近づいてください')
                    else:
                        self.label_msg.config(text='')
                        self.cycle_proc_state = CycleProcState.THERMISTOR

                    self.label_distance.config(text='距離：' + str(self.distance) + ' cm ')

        # サーミスタ温度
        elif self.cycle_proc_state == CycleProcState.THERMISTOR:
            self.thermistor_temp = round(self.thermal_sensor.temperature, 2)
            self.label_thermistor.config(text='サーミスタ温度：' + str(self.thermistor_temp) + ' ℃')
            self.cycle_proc_state = CycleProcState.TEMPERATURE

        # 赤外線センサ温度
        elif self.cycle_proc_state == CycleProcState.TEMPERATURE:
            self.temperature[self.temperature_index] = round(np.amax(np.array(self.thermal_sensor.pixels)), 2)
            self.cycle_proc_state = CycleProcState.DUMMY
        
        # ダミー
        elif self.cycle_proc_state == CycleProcState.DUMMY:
            if self.temperature_index == 0:
                print('センサ温度')
                print(*self.thermal_sensor.pixels, sep='\n')
                self.label_temperature_0.config(text='センサ温度(1回目)：' + str(self.temperature[0]) + '℃')
                self.temperature_index = 1
                self.cycle_proc_state = CycleProcState.TEMPERATURE
            elif self.temperature_index == 1:
                self.label_temperature_1.config(text='センサ温度(2回目)：' + str(self.temperature[1]) + '℃')
                self.temperature_index = 2
                self.cycle_proc_state = CycleProcState.TEMPERATURE
            elif self.temperature_index == 2:
                self.label_temperature_2.config(text='センサ温度(3回目)：' + str(self.temperature[2]) + '℃')
                self.temperature_index = 0
                self.cycle_proc_state = CycleProcState.MAKE_BODY_TEMP
            else:
                # 設計上ありえないがロバスト性に配慮
                print('[error] index')
                self.temperature_index = 0
                self.cycle_proc_state = CycleProcState.FACE_DETECTION               

       # 体温演算
        elif self.cycle_proc_state == CycleProcState.MAKE_BODY_TEMP:
            # 赤外線センサ温度(中央値)
            self.temperature.sort()
            self.temperature_med = round(self.temperature[1], 2)
            self.label_temperature_med.config(text='センサ温度(中央値)：' + str(self.temperature_med) + '℃')
            # サーミスタ温度補正
            diff = BODY_TEMP_STANDARD - self.temperature_med
            corr = diff - self.thermistor_corr
            print(corr)
            self.thermistor_corr = round((self.thermistor_corr + (corr / 10)), 2)
            self.label_thermistor_corr.config(text='サーミスタ温度補正：' + str(self.thermistor_corr) + ' ℃')
            # 体温
            self.body_temp = round((self.temperature_med + self.thermistor_corr), 1)
            self.label_body_tmp.config(text='体温：' + str(self.body_temp) + '℃')
            if self.body_temp > 38.0:
                    self.label_msg.config(text='体温が高いです！検温してください')
            elif self.body_temp < 35.0:
                self.label_msg.config(text='体温が低いです！検温してください')
            else:
                self.label_msg.config(text='体温は正常です！問題ありません')

            self.cycle_proc_state = CycleProcState.UPDATE_CSV
   
        # CSV更新
        elif self.cycle_proc_state == CycleProcState.UPDATE_CSV:
            self.csv_ctrl()
            self.cycle_proc_state = CycleProcState.PAUSE

        # 一時停止
        elif self.cycle_proc_state == CycleProcState.PAUSE:
            # カメラ映像の空読み
            self.camera_clear_frame()
            self.pause_timer += 1
            if self.pause_timer > 10:
                self.pause_timer = 0
                # 計測データ ウィジット 初期化
                self.init_param_widgets()
                self.cycle_proc_state = CycleProcState.FACE_DETECTION

        # 設計上ありえないがロバスト性に配慮
        else:
            print('[error] cycle_proc')
            self.cycle_proc_state = CycleProcState.FACE_DETECTION

        # 周期処理
        self.after(PROC_CYCLE, self.cycle_proc)

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    app.mainloop()