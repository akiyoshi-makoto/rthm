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

##############################################################################
# 定数
##############################################################################
PROC_CYCLE = 50                     # 処理周期[msec]

# 周期処理状態
class CycleProcState(Enum):
    FACE_DETECTION = 0              # 顔検出
    PAUSE = 1                       # 一時停止

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
        # 一時停止タイマ
        self.pause_timer = 0

        # ウィジットを生成
        self.create_widgets()
        # カメラ
        self.camera_init()
        
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
        h = 860                             # ウィンドウの高さ
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

        self.label_temperature_0 = ttk.Label(frame_lower)
        self.label_temperature_0.grid(row=0, sticky='NW')
        self.label_temperature_1 = ttk.Label(frame_lower)
        self.label_temperature_1.grid(row=1, sticky='NW')
        self.label_temperature_2 = ttk.Label(frame_lower)
        self.label_temperature_2.grid(row=2, sticky='NW')
        self.label_temperature_3 = ttk.Label(frame_lower)
        self.label_temperature_3.grid(row=3, sticky='NW')
        self.label_temperature_4 = ttk.Label(frame_lower)
        self.label_temperature_4.grid(row=4, sticky='NW')
        self.label_temperature_med = ttk.Label(frame_lower)
        self.label_temperature_med.grid(row=5, sticky='NW')
        self.label_distance = ttk.Label(frame_lower)
        self.label_distance.grid(row=6, sticky='NW')
        self.label_distance_corr = ttk.Label(frame_lower)
        self.label_distance_corr.grid(row=7, sticky='NW')
        self.label_thermistor = ttk.Label(frame_lower)
        self.label_thermistor.grid(row=8, sticky='NW')
        self.label_thermistor_corr = ttk.Label(frame_lower)
        self.label_thermistor_corr.grid(row=9, sticky='NW')

        self.init_param_widgets()

    ##########################################################################
    # 計測データ ウィジット 初期化
    ##########################################################################
    def init_param_widgets(self):        
        # フレーム(上部)
        self.label_msg.config(text='顔が白枠に合うよう近づいてください')
        self.label_body_tmp.config(text='体温：--.-- ℃')
        # フレーム(下部)
        self.label_temperature_0.config(text='センサ温度(1回目)：--.-- ℃')
        self.label_temperature_1.config(text='センサ温度(2回目)：--.-- ℃')
        self.label_temperature_2.config(text='センサ温度(3回目)：--.-- ℃')
        self.label_temperature_3.config(text='センサ温度(4回目)：--.-- ℃')
        self.label_temperature_4.config(text='センサ温度(5回目)：--.-- ℃')
        self.label_temperature_med.config(text='センサ温度(中央値)：--.-- ℃')
        self.label_distance.config(text='距離：--- cm')
        self.label_distance_corr.config(text='距離補正：--.-- ℃')
        self.label_thermistor.config(text='サーミスタ温度：--.-- ℃')
        self.label_thermistor_corr.config(text='サーミスタ温度補正：--.-- ℃')

    ##########################################################################
    # カメラ初期化
    ##########################################################################
    def camera_init(self):   
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # print(self.camera.get(cv2.CAP_PROP_FPS))

        # 顔検出のための学習元データを読み込む
        self.face_cascade = cv2.CascadeClassifier('haarcascades/haarcascade_frontalface_default.xml')

    ##########################################################################
    # カメラ映像の空読み
    ##########################################################################
    def camera_clear_frame(self):
        ret, frame = self.camera.read()

    ##########################################################################
    # 顔認識処理
    ##########################################################################
    def face_recognition(self):
        # カメラ映像を取得
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
                            (0, 0, 255),
                            thickness=5)

        # ガイド枠の描画
        cv2.rectangle(frame_color, (60,60), (420,420), (255,255,255), thickness=5)
        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_color))
        # Pillow Photo -> Canvas
        self.canvas_camera.create_image(0, 0, image = self.photo, anchor = 'nw')

        return len(facerect)

    ##########################################################################
    # 周期処理
    ##########################################################################
    def cycle_proc(self):
        # 顔検出
        if self.cycle_proc_state == CycleProcState.FACE_DETECTION:
            # 顔認識処理
            facerect = self.face_recognition()

            if facerect > 0:
                self.cycle_proc_state = CycleProcState.PAUSE

        # 一時停止
        elif self.cycle_proc_state == CycleProcState.PAUSE:
            # カメラ映像の空読み
            self.camera_clear_frame()
            self.pause_timer += 1
            if self.pause_timer > 50:
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