#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
import time
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
        # 検出温度(最大値)
        self.pixels_max = 0.0
        # 体温
        self.body_temp = 0.0
        # サーミスタ温度
        self.thermistor_temp = 0.0
        # オフセット値
        self.offset_temp = 0.0

        self.pack()
        # ウィンドウをスクリーンの中央に配置
        self.setting_window(master)
        # ウィジットを生成
        self.create_widgets()
        # デバイスの初期化
        self.init_device()
        
        if self.video_camera.isOpened():
            # 周期処理
            self.cycle_proc()
        else:
            print('カメラ認識エラー')

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
        
        self.label_sns_tmp = ttk.Label(frame_lower)
        self.label_sns_tmp.grid(row=0, sticky='NW')
        self.label_env_tmp = ttk.Label(frame_lower)
        self.label_env_tmp.grid(row=1, sticky='NW')
        self.label_offset_tmp = ttk.Label(frame_lower)
        self.label_offset_tmp.grid(row=2, sticky='NW')
        self.label_body_tmp = ttk.Label(frame_lower)
        self.label_body_tmp.grid(row=3, sticky='NW')
        self.init_param_widgets()

        print('検出温度(最大値)：　サーミスタ温度：　オフセット値：　体温：')

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):        
        self.label_sns_tmp.config(text='検出温度(最大値)：--.- ℃')
        self.label_env_tmp.config(text='サーミスタ温度：--.- ℃')
        self.label_offset_tmp.config(text='オフセット値：--.- ℃')
        self.label_body_tmp.config(text='体温：--.- ℃')
    
    ##########################################################################
    # 計測データ ウィジット 表示更新
    ##########################################################################
    def update_param_widgets(self):
        self.label_sns_tmp.config(text='検出温度(最大値)：' + str(self.pixels_max) + ' ℃')
        self.label_env_tmp.config(text='サーミスタ温度：' + str(self.thermistor_temp) + ' ℃')
        self.label_offset_tmp.config(text='オフセット値：' + str(self.offset_temp) + ' ℃')
        self.label_body_tmp.config(text='体温：' + str(self.body_temp) + ' ℃')
        
        print(str(self.pixels_max) + '  ' +
              str(self.thermistor_temp) + '  ' +
              str(self.offset_temp) +  '  ' +
              str(self.body_temp))

    ##########################################################################
    # デバイスの初期化
    ##########################################################################
    def init_device(self):   
        # ビデオカメラ
        self.init_video_camera()
        # サーマルセンサ(AMG8833)
        self.init_thermal_sensor()

    ##########################################################################
    # ビデオカメラ　初期化
    ##########################################################################
    def init_video_camera(self):   
        self.video_camera = cv2.VideoCapture(0)
        self.video_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.video_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # print(self.video_camera.get(cv2.CAP_PROP_FPS))

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
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        if self.pause_timer == 0:
            # 停止画取得処理
            self.read_video_frame()
            # 顔認識処理
            self.detect_face()
            # 計測データ ウィジット 初期化
            self.init_param_widgets()
            self.the_world_timer = 0

        elif self.pause_timer < 10:
            self.pause_timer -= 1
            # 停止画取得処理
            # バッファに停止画が残っている場合を想定して顔認識をせずに停止画取得のみ行う
            self.read_video_frame()

        elif self.pause_timer >= 10:
            self.pause_timer -= 1

            # ザ・ワールド !!!!
            if self.the_world_timer == 0:
                # サーマルセンサ(AMG8833) サーミスタ制御
                self.ctrl_thermal_thermistor()
            elif self.the_world_timer == 1:
                # サーマルセンサ(AMG8833) 赤外線アレイセンサ制御
                self.ctrl_thermal_temperature()
            elif self.the_world_timer == 2:    
                # 計測データ 表示更新
                self.update_param_widgets()
            else:
                pass

            self.the_world_timer += 1

        else:
            # 設計上、負の値になることはないが、ロバスト性に配慮
            self.pause_timer = 0
            self.the_world_timer = 0

        # 周期処理
        self.after(PROC_CYCLE, self.cycle_proc)

    ##########################################################################
    # 停止画取得処理
    ##########################################################################
    def read_video_frame(self):
        # ビデオカメラの停止画を取得
        ret, self.frame = self.video_camera.read()
    
    ##########################################################################
    # 顔認識処理
    ##########################################################################
    def detect_face(self):
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
            # 一時停止してその間にサーマルセンサ制御を実行する
            self.pause_timer = FACE_DETECTIION_PAUSE
            # 検出した場所すべてに緑色で枠を描画する
            for rect in facerect:
                cv2.rectangle(frame_color,
                                tuple(rect[0:2]),
                                tuple(rect[0:2]+rect[2:4]),
                                (0, 255, 0),
                                thickness=3)

        else:
            self.pause_timer = 0

        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas_video.create_image(0, 0, image = self.photo, anchor = 'nw')


    ##########################################################################
    # サーマルセンサ(AMG8833) サーミスタ制御
    ##########################################################################
    def ctrl_thermal_thermistor(self):
        # サーミスタ温度
        self.thermistor_temp = round(self.sensor.temperature, 1)     

    ##########################################################################
    # サーマルセンサ(AMG8833) 赤外線アレイセンサ制御
    ##########################################################################
    def ctrl_thermal_temperature(self):
        # 検出温度
        pixels_array = np.array(self.sensor.pixels)
        # 検出温度(最大値)
        self.pixels_max = np.amax(pixels_array)
        # サーミスタ温度補正
        self.offset_temp = round((-0.6857 * self.thermistor_temp + 28), 1)
        # 体温
        self.body_temp = round((self.pixels_max + self.offset_temp), 1)

        # print(self.body_temp_array)

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    app.mainloop()