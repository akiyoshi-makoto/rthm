#!/usr/bin/env python
from tkinter import *
from tkinter import ttk
import cv2
import PIL.Image, PIL.ImageTk


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
        # カメラモジュールの映像を表示するキャンバスを用意する
        self.canvas = Canvas(self, width=480, height=480)
        self.canvas.pack(pady=10)

        label1 = ttk.Label(self, text='サーミスタ温度')
        label1.pack(pady=(5,0))

        label2 = ttk.Label(self, text='対象物までの距離:')
        label2.pack(pady=(5,0))

    ############################################################
    # デバイスの初期化
    ############################################################
    def init_device(self):   
        # カメラ
        self.init_camera()

    ############################################################
    # デバイスの初期化(カメラ)
    ############################################################
    def init_camera(self):   
        self.camera = cv2.VideoCapture(0)
        self.camera.set(3, 480) # set video widht
        self.camera.set(4, 480) # set video height
    
    ############################################################
    # 閉じるボタンが押下された場合の処理
    ############################################################
    def on_closing(self):
        # 周期処理を停止、終了処理後、メインウインドウを閉じる
        self.cycle_proc_exec = False

    ############################################################
    # 周期処理
    ############################################################
    def cycle_proc(self):
        # 周期処理実行許可
        if self.cycle_proc_exec:
            # カメラ制御
            self.ctrl_camera()
            # 30ms後に遅れて処理
            self.after(30,self.cycle_proc)
        else:
            # 終了処理
            self.camera.release()
            # メインウインドウを閉じる
            end_appication()

    ############################################################
    # カメラ制御
    ############################################################
    def ctrl_camera(self):
        # カメラの停止画を取得
        _, frame = self.camera.read()
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
# メインウインドウを閉じる
############################################################
def end_appication():
    root.destroy()

if __name__ == "__main__":
    root = Tk()
    app = Application(master=root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()