#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
import time
import datetime
import os
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
I2C_ADR = 0x68              # I2C アドレス
PROC_CYCLE = 30             # 処理周期[msec]
FACE_DETECTIION_PAUSE = 100 # 顔検出時の一時停止周期[30msec*100=3000msec]
BODY_TEMP_STANDARD = 36.2   # 体温の基準値[℃]
LOG_PATH = './log_file/'

##############################################################################
# クラス：Application
##############################################################################
class Application(ttk.Frame):
    def __init__(self, master=None):
        ttk.Frame.__init__(self, master)

        # 顔検出時の一時停止タイマ
        self.pause_timer = 0
        # 一時停止中の経過時間
        self.the_world_timer = 0
        # 検出温度
        self.sensor_temp = [BODY_TEMP_STANDARD, BODY_TEMP_STANDARD]
        # 検出温度(平均値)
        self.sensor_temp_ave = BODY_TEMP_STANDARD
        # 体温
        self.body_temp = BODY_TEMP_STANDARD
        # サーミスタ温度
        self.thermistor_temp = 0.0
        # オフセット値
        self.offset_temp = 0.0
        # 基準体温との差分
        self.standard_diff = 0.0

        self.pack()
        # ウィンドウをスクリーンの中央に配置
        self.setting_window(master)
        # ウィジットを生成
        self.create_widgets()
        # デバイスの初期化
        self.init_device()
        # CSV出力の初期設定
        self.init_csv()
        
        if self.camera.isOpened():
            # 周期処理
            self.cycle_proc()
        else:
            messagebox.showerror('カメラ認識エラー', 'カメラの接続を確認してください')

    ##########################################################################
    # ウィンドウをスクリーンの中央に配置
    ##########################################################################
    def setting_window(self, master):
        w = 500                             # ウィンドウの横幅
        h = 760                             # ウィンドウの高さ
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
        
        self.label_sns_tmp1 = ttk.Label(frame_lower)
        self.label_sns_tmp1.grid(row=0, sticky='NW')
        self.label_sns_tmp2 = ttk.Label(frame_lower)
        self.label_sns_tmp2.grid(row=1, sticky='NW')
        self.label_sns_tmp_ave = ttk.Label(frame_lower)
        self.label_sns_tmp_ave.grid(row=2, sticky='NW')
        self.label_env_tmp = ttk.Label(frame_lower)
        self.label_env_tmp.grid(row=3, sticky='NW')
        self.label_offset_tmp = ttk.Label(frame_lower)
        self.label_offset_tmp.grid(row=4, sticky='NW')
        self.label_standard_diff = ttk.Label(frame_lower)
        self.label_standard_diff.grid(row=5, sticky='NW')

        self.init_param_widgets()

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):        
        self.label_msg.config(text='顔が青枠に合うよう近づいてください')
        self.label_body_tmp.config(text='体温：--.-- ℃')
        self.label_sns_tmp1.config(text='検出温度(1回目)：--.-- ℃')
        self.label_sns_tmp2.config(text='検出温度(2回目)：--.-- ℃')
        self.label_sns_tmp_ave.config(text='検出温度(平均値)：--.-- ℃')
        self.label_env_tmp.config(text='サーミスタ温度：--.-- ℃')
        self.label_offset_tmp.config(text='オフセット値：--.-- ℃')
        self.label_standard_diff.config(text='基準体温との差分：--.-- ℃')
    
    ##########################################################################
    # 計測データ ウィジット 表示更新
    ##########################################################################
    def update_param_widgets(self):
        self.label_sns_tmp1.config(text='検出温度(1回目)：' + str(self.sensor_temp[0]) + ' ℃')
        self.label_sns_tmp2.config(text='検出温度(2回目)：' + str(self.sensor_temp[1]) + ' ℃')
        self.label_sns_tmp_ave.config(text='検出温度(平均値)：' + str(self.sensor_temp_ave) + ' ℃')
        self.label_env_tmp.config(text='サーミスタ温度：' + str(self.thermistor_temp) + ' ℃')
        self.label_offset_tmp.config(text='オフセット値：' + str(self.offset_temp) + ' ℃')
        self.label_standard_diff.config(text='基準体温との差分：' + str(self.standard_diff) + ' ℃')

        self.label_body_tmp.config(text='体温：' + str(self.body_temp) + ' ℃')

        if self.body_temp >= 38.0:
            self.label_msg.config(text='体温が高いので、検温をお願いします')
        else:
            self.label_msg.config(text='体温は正常です')
        
        # print(str(self.sensor_temp[0]) + ',' +
        #       str(self.sensor_temp[1]) + ',' +
        #       str(self.sensor_temp_ave) + ',' +
        #       str(self.thermistor_temp) + ',' +
        #       str(self.offset_temp) +  ',' +
        #       str(self.standard_diff) +  ',' +
        #       str(self.body_temp))

        # CSV出力
        self.csv_output()

    ##########################################################################
    # デバイスの初期化
    ##########################################################################
    def init_device(self):   
        # カメラ
        self.init_camera()
        # サーマルセンサ(AMG8833)
        self.init_thermal_sensor()

    ##########################################################################
    # カメラ　初期化
    ##########################################################################
    def init_camera(self):   
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # print(self.camera.get(cv2.CAP_PROP_FPS))

        # 顔検出のための学習元データを読み込む
        self.face_cascade = cv2.CascadeClassifier('haarcascades/haarcascade_frontalface_default.xml')

    ##########################################################################
    # サーマルセンサ(AMG8833) 初期化
    ##########################################################################
    def init_thermal_sensor(self):   
        # I2Cバスの初期化
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        # センサの初期化
        self.sensor = adafruit_amg88xx.AMG88XX(i2c_bus, addr=I2C_ADR)
        # センサの初期化待ち
        time.sleep(.1)

    ##########################################################################
    # CSV出力の初期設定
    ##########################################################################
    def init_csv(self):
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
            file.writerow(['検出温度(1回目)','検出温度(2回目)','検出温度(平均値)',
                           'サーミスタ温度','オフセット値','基準体温との差分','体温'])

    ##########################################################################
    # CSV出力
    ##########################################################################
    def csv_output(self):
        # csvファイルの生成
        with open(self.filename, 'a', newline='') as csvfile:
            file = csv.writer(csvfile)
            # csvファイルへの書き込みデータ
            data = [self.sensor_temp[0],self.sensor_temp[1],self.sensor_temp_ave,
                    self.thermistor_temp,self.offset_temp,self.standard_diff,self.body_temp]
            # データの書き込み
            file.writerow(data)

    ##########################################################################
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        if self.pause_timer == 0:
            # 計測データ ウィジット 初期化
            self.init_param_widgets()
            # 停止画取得
            self.camera_get_frame()
            # 顔認識処理
            is_detect = self.camera_detect_face()

            if is_detect:
                # 一時停止している間に体温を測定する
                self.pause_timer = FACE_DETECTIION_PAUSE
            else:
                self.pause_timer = 0
            
            self.the_world_timer = 0

        elif self.pause_timer < 10:
            # 停止画取得
            # バッファに停止画が残っている場合を想定して顔認識をせずに停止画取得のみ行う
            self.camera_get_frame()

            self.pause_timer -= 1
            self.the_world_timer = 0

        elif self.pause_timer >= 10:
            # ザ・ワールド !!!!
            if self.the_world_timer == 0:
                # サーマルセンサ(AMG8833) 赤外線アレイセンサ 温度取得(1回目)
                self.thermal_get_temperature(0)
            elif self.the_world_timer == 1:
                # サーマルセンサ(AMG8833) サーミスタ 温度取得
                self.thermal_get_thermistor()
            elif self.the_world_timer < 10:
                pass
            elif self.the_world_timer == 10:
                # サーマルセンサ(AMG8833) 赤外線アレイセンサ 温度取得(2回目)
                self.thermal_get_temperature(1)
            elif self.the_world_timer == 11:
                # サーマルセンサ(AMG8833) 体温の算出
                self.thermal_make_body_temp()
            elif self.the_world_timer == 12:
                # 計測データ 表示更新
                self.update_param_widgets()
            else:
                # そして時は動き出す・・・
                pass

            self.pause_timer -= 1
            self.the_world_timer += 1

        else:
            # 設計上、負の値になることはないが、ロバスト性に配慮
            self.pause_timer = 0
            self.the_world_timer = 0

        # 周期処理
        self.after(PROC_CYCLE, self.cycle_proc)

    ##########################################################################
    # 停止画取得
    ##########################################################################
    def camera_get_frame(self):
        # 停止画を取得
        ret, self.frame = self.camera.read()
    
    ##########################################################################
    # 顔認識処理
    ##########################################################################
    def camera_detect_face(self):
        # 左右反転
        frame_mirror = cv2.flip(self.frame, 1)
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
            is_detect = True
            # 検出した場所すべてに緑色で枠を描画する
            for rect in facerect:
                cv2.rectangle(frame_color,
                                tuple(rect[0:2]),
                                tuple(rect[0:2]+rect[2:4]),
                                (0, 255, 0),
                                thickness=3)
            
            # print(rect)
        else:
            is_detect = False

        # ガイド枠の描画
        cv2.rectangle(frame_color, (60,60), (420,420), (0,0,255), thickness=3)
        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas_camera.create_image(0, 0, image = self.photo, anchor = 'nw')

        return is_detect

    ##########################################################################
    # サーマルセンサ(AMG8833) サーミスタ 温度取得
    ##########################################################################
    def thermal_get_thermistor(self):
        # サーミスタ温度
        self.thermistor_temp = round(self.sensor.temperature, 2)     

    ##########################################################################
    # サーマルセンサ(AMG8833) 赤外線アレイセンサ 温度取得
    ##########################################################################
    def thermal_get_temperature(self, index):
        # 検出温度
        temp = np.array(self.sensor.pixels)
        # ガイド枠の内側部分で検出した温度のみを採用
        # temp_select = temp[1:7,1:7]
        # print(temp)
        # print(temp_select)
        # 検出温度(最大値)
        self.sensor_temp[index] = np.amax(temp)

    ##########################################################################
    # サーマルセンサ(AMG8833) 体温の算出
    ##########################################################################
    def thermal_make_body_temp(self):
        # 検出温度　平均値
        self.sensor_temp_ave = round((self.sensor_temp[0] + self.sensor_temp[1]) / 2, 2)
        # 基準体温との差分
        self.standard_diff = round((BODY_TEMP_STANDARD - self.sensor_temp_ave), 2)
        # サーミスタ温度補正
        self.offset_temp = round((0.8424 * self.thermistor_temp - 3.2523), 2)
        # 体温
        self.body_temp = round((self.sensor_temp_ave + self.offset_temp), 1)

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    app.mainloop()