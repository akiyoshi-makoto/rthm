#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
import time
import RPi.GPIO as GPIO
import busio
import board
import adafruit_amg88xx
import cv2
import PIL.Image, PIL.ImageTk

############################################################
# 定数
############################################################
TRIG = 27
ECHO = 22

class Application(ttk.Frame):
    def __init__(self, master=None):
        ttk.Frame.__init__(self, master)
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
        # ビデオカメラの映像を表示するキャンバスを用意する
        self.canvas = Canvas(self, width=480, height=480)
        self.canvas.pack(pady=10)

        self.label_tgt_tmp = ttk.Label(self, text='体温：')
        self.label_tgt_tmp.pack(pady=(5,0))

        self.label_env_tmp = ttk.Label(self, text='サーミスタ温度：')
        self.label_env_tmp.pack(pady=(5,0))

        self.label_distance = ttk.Label(self, text='対象物までの距離：')
        self.label_distance.pack(pady=(5,0))

    ############################################################
    # デバイスの初期化
    ############################################################
    def init_device(self):   
        # GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        # 超音波センサ
        self.init_ultra_sonic_sensor()
        # サーマルカメラ
        self.init_thermal_camera()
        # ビデオカメラ
        self.init_video_camera()

    ############################################################
    # デバイスの初期化(超音波センサ)
    ############################################################
    def init_ultra_sonic_sensor(self):
        # GPIO端子の初期設定
        GPIO.setup(TRIG,GPIO.OUT)
        GPIO.setup(ECHO,GPIO.IN)
        GPIO.output(TRIG, GPIO.LOW)

    ############################################################
    # 超音波センサ制御
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
        distance = echo_pulse_width / 58

        self.label_distance.config(text='対象物までの距離：' + str(round(distance)))

    ############################################################
    # デバイスの初期化(サーマルカメラ)
    ############################################################
    def init_thermal_camera(self):   
        # I2Cバスの初期化
        self.i2c_bus = busio.I2C(board.SCL, board.SDA)

    ############################################################
    # サーマルカメラ制御
    ############################################################
    def ctrl_thermal_camera(self):
        # センサーの初期化：I2Cスレーブアドレス(0x68)
        self.sensor = adafruit_amg88xx.AMG88XX(self.i2c_bus, addr=0x68)
        # 8x8センサアレイ内の最大温度を取得
        max_temp = max(max(self.sensor.pixels))

        self.label_tgt_tmp.config(text='体温：' + str(round(max_temp)))

    ############################################################
    # デバイスの初期化(ビデオカメラ)
    ############################################################
    def init_video_camera(self):   
        self.video_camera = cv2.VideoCapture(0)
        self.video_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
        self.video_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ############################################################
    # ビデオカメラ制御
    ############################################################
    def ctrl_video_camera(self):
        # ビデオカメラの停止画を取得
        _, frame = self.video_camera.read()
        frame_orgn = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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
                cv2.rectangle(frame_orgn, tuple(rect[0:2]), tuple(rect[0:2]+rect[2:4]), (0, 0, 255), thickness=3)
        # OpenCV frame -> Pillow Photo
        self.photo = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame_orgn))
        # Pillow Photo -> Canvas
        self.canvas.create_image(0, 0, image = self.photo, anchor = 'nw')

    ############################################################
    # 閉じるボタンが押下された場合の処理
    ############################################################
    def on_close_button(self):
        # 周期処理を停止、終了処理後、メインウインドウを閉じる
        self.cycle_proc_exec = False

    ############################################################
    # 周期処理
    ############################################################
    def cycle_proc(self):
        # 周期処理実行許可
        if self.cycle_proc_exec:
            # 超音波センサ
            self.ctrl_ultra_sonic_sensor()
            # サーマルカメラ制御
            self.ctrl_thermal_camera()
            # ビデオカメラ制御
            self.ctrl_video_camera()
            # 1000ms後に遅れて処理
            self.after(1000,self.cycle_proc)
        else:
            # 終了処理
            self.video_camera.release()
            # メインウインドウを閉じる
            close_main_window()

############################################################
# メインウインドウを閉じる
############################################################
def close_main_window():
    root.destroy()

if __name__ == '__main__':
    root = Tk()
    app = Application(master=root)
    root.protocol('WM_DELETE_WINDOW', app.on_close_button)
    app.mainloop()