import time
import socket
import threading
import sys
import getopt
import os
import re
import random
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel
from PyQt5.QtGui import QPixmap

from Window import Ui_MainWindow
from RtpPacket import *

DISPLAY_MODE = False

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

SERVER_ADDR = '127.0.0.1'
SERVER_PORT = 9999
RTP_MIN_PORT = 5000
RTP_MAX_PORT = 10000
RTP_PACKET_MAX_SIZE = 51200

SAVE_FILE_PATH = './save/'
CACHE_FILE_PATH = './cache/'
CACHE_FILE_NAME = 'ClientCache-'
CACHE_FILE_EXT = '.jpg'


class Client(QMainWindow, Ui_MainWindow):
    """ 客户端类 """
    # 客户端状态宏定义
    INIT = 0  # 初始化
    READY = 1  # 准备就绪
    PLAYING = 2  # 正在播放
    PAUSING = 3  # 正在暂停
    # RTSP 命令宏定义
    NONE = -1  # NONE 命令
    DESCRIBE = 0  # DESCRIBE 命令
    SETUP = 1  # SETUP 命令
    PLAY = 2  # PLAY 命令
    PAUSE = 3  # PAUSE 命令
    TEARDOWN = 4  # TEARDOWN 命令

    def __init__(self, server_addr, server_port):
        """ 类构造方法 """
        # --- 基类初始化 ---
        super(Client, self).__init__()
        # --- RTSP/TCP 初始化 ---
        self.server_addr = server_addr  # 服务端 地址
        self.server_port = int(server_port)  # 服务端 端口
        self.rtsp_socket = None  # RTSP/TCP 套接字
        self.rtsp_seq = 0  # RTSP/TCP 请求序列号
        self.rtsp_request = ''  # RTSP/TCP 请求（字符串）
        self.rtsp_request_code = self.NONE  # RTSP/TCP 请求代码
        self.rtsp_reply = {}  # RTSP/TCP 回复（字典）
        self.session_id = '0'  # RTSP/TCP 会话标识
        # --- RTP/UDP 初始化 ---
        self.rtp_server_port = 0  # RTP/UDP 服务端端口
        self.rtp_client_port = 0  # RTP/UDP 客户端端口
        self.rtp_socket = None  # RTP/UDP 套接字
        self.rtp_thread = None  # RTP/UDP 当前线程
        self.rtp_play_event = threading.Event()  # RTP/UDP 播放事件
        self.rtp_teardown_flag = False  # RTP/UDP 线程关闭标识
        self.rtp_data_buffer = bytearray()  # RTP/UDP 数据缓存区
        self.rtp_data_buffer_number = 0  # RTP/UDP 数据缓存区标记
        self.filename = ''  # 文件名（URL）
        self.subtitle = ''  # 文件字幕
        self.subtitle_mode = False  # 字幕模式（全局设置）
        self.compress_mode = False  # 压缩模式（全局设置）
        self.frame_speed = 1.0  # 播放速率（全局设置）
        self.frame_count = 0  # 帧总数量
        self.frame_number = 0  # 当前帧序号
        self.subtitle_adjust = 0  # 字幕调节
        # --- 客户端 初始化 ---
        self.state = self.INIT  # 客户端 初始状态
        self.play_list = []  # 播放列表
        # --- GUI初始化 ---
        self.playback_rate_list = None
        self.subtitle_adjust_list = None
        self.label_Subtitle = None
        self.initWindow()
        self.updateWindow()
        # 连接到客户端
        if not self.createRtspConnection():
            QMessageBox.critical(self, '连接失败', '服务端（IP = %s, port = %s）连接失败！' % (server_addr, server_port), QMessageBox.Yes, QMessageBox.Yes)
            quit()
        # 更新播放列表
        self.sendRtspRequest(self.DESCRIBE)

    def initWindow(self):
        """ 初始化 GUI 窗口 """
        # UI 初始化
        self.playback_rate_list = ['播放速度 <1.0>', '播放速度 <0.5>', '播放速度 <0.75>', '播放速度 <1.25>', '播放速度 <1.5>', '播放速度 <2.0>']
        self.subtitle_adjust_list = ['字幕调节 <+0>', '字幕调节 <+0.2>', '字幕调节 <+0.5>', '字幕调节 <+1.0>', '字幕调节 <+2.0>',
                                     '字幕调节 <-0.2>', '字幕调节 <-0.5>', '字幕调节 <-1.0>', '字幕调节 <-2.0>']
        self.setupUi(self)
        self.label_Subtitle = QLabel('', self.label_Screen)
        self.label_Subtitle.setGeometry(0, 495, 1024, 81)
        self.label_Subtitle.setAlignment(Qt.AlignCenter)
        self.label_Subtitle.setStyleSheet('QLabel {background-color: transparent; font: 150 16pt "微软雅黑"; color: rgb(255, 255, 255) }')
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.label_Screen.keyPressEvent = self.keyPressEvent
        self.comboBox_PlaybackRate.addItems(self.playback_rate_list)
        self.comboBox_SubtitleAdjust.addItems(self.subtitle_adjust_list)
        self.listWidget_PlayList.addItems(self.play_list)
        self.slider_ProgressBar.setMinimum(0)
        self.slider_ProgressBar.setMaximum(1000)
        self.slider_ProgressBar.setValue(0)
        # 信号槽绑定
        self.pushButton_FullScreen.clicked.connect(self.__onFullScreenClicked)
        self.pushButton_PlayPause.clicked.connect(self.__onPlayPauseClicked)
        self.pushButton_Stop.clicked.connect(self.__onStopClicked)
        self.pushButton_Subtitle.clicked.connect(self.__onSubtitleClicked)
        self.pushButton_Compress.clicked.connect(self.__onCompressClicked)
        self.pushButton_Search.clicked.connect(self.__onSearchClicked)
        self.comboBox_PlaybackRate.currentIndexChanged.connect(self.__onPlaybackRateChanged)
        self.comboBox_SubtitleAdjust.currentIndexChanged.connect(self.__onSubtitleAdjustChanged)
        self.slider_ProgressBar.sliderPressed.connect(self.__onProgressBarPressed)
        self.slider_ProgressBar.sliderReleased.connect(self.__onProgressBarReleased)
        self.listWidget_PlayList.itemDoubleClicked.connect(self.__onListWidgetClicked)

    def updateWindow(self):
        # --- 信息栏更新 ---
        if self.state == self.INIT:
            self.label_InfoBar.setText('【INIT】未加载视频')
        elif self.state == self.READY:
            self.label_InfoBar.setText('【READY】已加载视频 - %s' % self.filename)
        elif self.state == self.PLAYING:
            self.label_InfoBar.setText('【PLAYING】正在播放 - %s' % self.filename)
        elif self.state == self.PAUSING:
            self.label_InfoBar.setText('【PAUSING】正在暂停 - %s' % self.filename)
        # --- 播放/暂停 按钮更新 ---
        # INIT|READY|PAUSING -- 播放按钮
        if self.state == self.INIT or self.state == self.READY or self.state == self.PAUSING:
            self.pushButton_PlayPause.setToolTip('播放')
            self.pushButton_PlayPause.setStyleSheet('QPushButton{border-image: url(./img/play.png)}'
                                                    'QPushButton:hover{border-image: url(./img/play_1.png)}'
                                                    'QPushButton:pressed{border-image: url(./img/play_2.png)}')
            self.pushButton_PlayPause.update()
        # PLAYING -- 暂停按钮
        elif self.state == self.PLAYING:
            self.pushButton_PlayPause.setToolTip('暂停')
            self.pushButton_PlayPause.setStyleSheet('QPushButton{border-image: url(./img/pause.png)}'
                                                    'QPushButton:hover{border-image: url(./img/pause_1.png)}'
                                                    'QPushButton:pressed{border-image: url(./img/pause_2.png)}')
            self.pushButton_PlayPause.update()
        # --- 屏幕更新 ---
        # INIT|READY -- 清空屏幕
        if self.state == self.INIT or self.state == self.READY:
            self.label_Screen.setPixmap(QPixmap(''))
        # --- 进度条更新 ---
        # INIT|READY -- 锁定为 0
        if self.state == self.INIT or self.state == self.READY:
            self.slider_ProgressBar.setValue(0)
        # --- 字幕更新 ---
        # INIT|READY -- 清空字幕
        if self.state == self.INIT or self.state == self.READY:
            self.label_Subtitle.setText('')

    def createRtspConnection(self):
        """ 创建 RTSP/TCP 连接 """
        if self.rtsp_socket:
            self.rtsp_socket.shutdown(socket.SHUT_RDWR)
            self.rtsp_socket.close()
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtsp_socket.connect((self.server_addr, self.server_port))
            threading.Thread(target=self.recvRtspReply).start()  # 派生线程  持续接收RTSP回复
            return True
        except:
            return False

    def sendRtspRequest(self, requestCode):
        """ 发送 RTSP/TCP 请求 """
        # DESCRIBE 命令
        if requestCode == self.DESCRIBE:
            self.rtsp_seq += 1
            line_1 = ['DESCRIBE', self.filename, 'RTSP/1.0']
            line_2 = ['CSeq:', str(self.rtsp_seq)]
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n'
            self.rtsp_request_code = self.DESCRIBE
        # SETUP 命令
        elif requestCode == self.SETUP:
            if not self.state == self.INIT:
                return False
            while not self.createRtpConnection():  # 建立 RTP 连接
                pass
            self.rtsp_seq += 1
            line_1 = ['SETUP', self.filename, 'RTSP/1.0']
            line_2 = ['CSeq:', str(self.rtsp_seq)]
            line_3 = ['Transport:', 'RTP/UDP;client_port=' + str(self.rtp_client_port)]
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
            self.rtsp_request_code = self.SETUP
        # PLAY 命令
        elif requestCode == self.PLAY:
            if not (self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING):
                return False
            if not self.__play():
                raise RuntimeError
            self.rtsp_seq += 1
            line_1 = ['PLAY', self.filename, 'RTSP/1.0']
            line_2 = ['CSeq:', str(self.rtsp_seq)]
            line_3 = ['Session:', str(self.session_id)]
            line_4 = ['Range:', 'npt=%s' % self.frame_number]
            line_5 = ['Speed:', str(self.frame_speed)]
            line_6 = ['Subtitle-Mode:', str(self.subtitle_mode)]
            line_7 = ['Compress-Mode:', str(self.compress_mode)]
            line_8 = ['Subtitle-Adjust:', str(self.subtitle_adjust)]
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n' + ' '.join(line_4) + '\n' \
                                + ' '.join(line_5) + '\n' + ' '.join(line_6) + '\n' + ' '.join(line_7) + '\n' + ' '.join(line_8) + '\n'
            self.rtsp_request_code = self.PLAY
        # PAUSE 命令
        elif requestCode == self.PAUSE:
            if not self.state == self.PLAYING:
                return
            if not self.__pause():
                raise RuntimeError
            self.rtsp_seq += 1
            line_1 = ['PAUSE', self.filename, 'RTSP/1.0']
            line_2 = ['CSeq:', str(self.rtsp_seq)]
            line_3 = ['Session:', str(self.session_id)]
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
            self.rtsp_request_code = self.PAUSE
        # TEARDOWN 命令
        elif requestCode == self.TEARDOWN:
            if not (self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING):
                return False
            self.rtsp_seq += 1
            line_1 = ['TEARDOWN', self.filename, 'RTSP/1.0']
            line_2 = ['CSeq:', str(self.rtsp_seq)]
            line_3 = ['Session:', str(self.session_id)]
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
            self.rtsp_request_code = self.TEARDOWN
        else:
            return False
        # 通过RTSP套接字发送命令
        self.rtsp_socket.send(self.rtsp_request.encode())
        if DISPLAY_MODE:
            print('\n@ Data sent:\n' + self.rtsp_request)
        return True

    def recvRtspReply(self):
        """ 接收 RTSP/TCP 回复（循环阻塞） """
        # 进行回复处理循环
        while True:
            # *** 接收 RTSP/TCP 回复  recvRtspReply ***
            try:
                reply = self.rtsp_socket.recv(1024)
            except OSError:
                break
            if not reply:
                break
            data = reply.decode('utf-8')
            if DISPLAY_MODE:
                print('\n@ Data recv:\n' + data)
            # *** 处理 RTSP/TCP 回复  handleRtspReply ***
            try:
                # 分析 RTSP/TCP 回复
                if not self.parseRtspReply(data):
                    raise KeyError
                # Code 判断
                if self.rtsp_reply['Code'] != '200':
                    raise RuntimeError
                # session_id 判断
                if (not self.rtsp_request_code == self.DESCRIBE) and (not self.rtsp_request_code == self.SETUP) and (not self.rtsp_request_code == self.TEARDOWN) \
                        and (not self.session_id == self.rtsp_reply['Session']):
                    raise KeyError
                # DESCRIBE  命令
                if self.rtsp_request_code == self.DESCRIBE:
                    if not self.__describe():
                        raise RuntimeError
                # SETUP 命令
                elif self.rtsp_request_code == self.SETUP:
                    if not self.__setup():
                        raise RuntimeError
                # PLAY 命令
                elif self.rtsp_request_code == self.PLAY:
                    pass
                # PAUSE 命令
                elif self.rtsp_request_code == self.PAUSE:
                    pass
                # TEARDOWN 命令
                elif self.rtsp_request_code == self.TEARDOWN:
                    if not self.__teardown():
                        raise RuntimeError
                # 其他命令
                else:
                    raise NotImplementedError
                # 更新 GUI
                self.updateWindow()
            except KeyError:
                print('@ 服务端错误：服务端（IP = %s, port = %s）回复格式错误！' % (self.server_addr, self.server_port))
            except NotImplementedError:
                print('@ 服务端错误：服务端（IP = %s, port = %s）未实现此命令！' % (self.server_addr, self.server_port))
            except RuntimeError:
                print('@ 服务端错误：服务端（IP = %s, port = %s）运行时错误！' % (self.server_addr, self.server_port))
        # 关闭连接套接字
        self.__teardown()
        try:
            self.rtsp_socket.shutdown(socket.SHUT_RDWR)
            self.rtsp_socket.close()
        except OSError:
            pass

    def parseRtspReply(self, data):
        """ 分析 RTSP/TCP 回复 """
        try:
            # 创建参数字典
            lines = str(data).split('\n')
            self.rtsp_reply = {'Code': lines[0].split(' ')[1], 'Describe': ' '.join(lines[0].split(' ')[2:])}
            if not self.rtsp_reply['Code'] == '200':
                return True
            else:
                self.rtsp_reply['CSeq'] = lines[1].split(' ')[1]
            # 字段信息提取
            for line in lines[1:]:
                words = line.split(' ')
                # 提取 Session
                if 'Session' in words[0]:
                    self.rtsp_reply['Session'] = words[1]
                # 提取 Transport
                elif 'Transport' in words[0]:
                    # 提取 server_port
                    pattern = re.compile(r'server_port=\s*(\S*?)\s*(;|$)')
                    result = pattern.search(line)
                    if result:
                        self.rtsp_reply['server_port'] = result.group(1)
                    else:
                        raise KeyError
                # 提取 List
                elif 'List' in words[0]:
                    self.rtsp_reply['List'] = ' '.join(words[1:])
                # 提取 Length
                elif 'Length' in words[0]:
                    self.rtsp_reply['Length'] = words[1]
            return True
        except KeyError:
            self.rtsp_reply = {}
            return False

    def createRtpConnection(self):
        """ 创建 RTP/UDP 连接 """
        # 创建 RTP/UDP 套接字
        if self.rtp_socket:
            self.rtp_socket.shutdown(socket.SHUT_RDWR)
            self.rtp_socket.close()
            self.rtp_socket = None
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RTP_PACKET_MAX_SIZE)
        try:
            # 绑定套接字  使用随机的端口
            self.rtp_client_port = random.randint(RTP_MIN_PORT, RTP_MAX_PORT)
            self.rtp_socket.bind(("", self.rtp_client_port))
            return True
        except OSError:
            # TODO 错误处理
            self.rtp_socket = None
            return False

    def handleRtpConnection(self):
        """ 处理 RTP/UDP 连接 """
        while True:
            try:
                self.rtp_play_event.wait()
                if self.rtp_teardown_flag:
                    raise OSError
                data, addr = self.rtp_socket.recvfrom(65535)
                if data:
                    rtp_packet = RtpPacket()
                    rtp_packet.decode(data)
                    # --JPEG--
                    if rtp_packet.payload_type() == PT_JPEG:
                        if not rtp_packet.frame() == self.rtp_data_buffer_number:
                            self.rtp_data_buffer.clear()
                            self.rtp_data_buffer_number = rtp_packet.frame()
                        self.rtp_data_buffer.extend(rtp_packet.get_payload())
                        if rtp_packet.frame() >= self.frame_count - 30:
                            break
                        if rtp_packet.marker() == 1:
                            if self.frame_number <= rtp_packet.frame() <= self.frame_number + 30:
                                self.frame_number = rtp_packet.frame()
                                if DISPLAY_MODE:
                                    print('@ %s' % self.frame_number)
                                if rtp_packet.size() == len(self.rtp_data_buffer):
                                    self.updateScreen(self.writeFrame(self.rtp_data_buffer), self.subtitle)
                                self.rtp_data_buffer.clear()
                    # --TEXT--
                    elif rtp_packet.payload_type() == PT_TEXT:
                        self.subtitle = rtp_packet.get_payload().decode('utf-8')
            except OSError:
                break
        if DISPLAY_MODE:
            print('@ 客户端 RTP 线程已退出')
        self.__teardown()
        self.state = self.INIT
        self.updateWindow()

    def writeFrame(self, data):
        cache_name = CACHE_FILE_PATH + CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT
        while True:
            try:
                file = open(cache_name, "wb")
                file.write(data)
                file.close()
            except OSError or PermissionError:
                continue
            break
        return cache_name

    def updateScreen(self, pixmap_path, subtitle):
        """ GUI 屏幕更新 """
        # 进度条更新
        if self.frame_count == 0:
            self.slider_ProgressBar.setValue(0)
        else:
            progress = round(self.frame_number * 1000 / self.frame_count)
            if progress < 0:
                self.slider_ProgressBar.setValue(0)
            elif progress > 1000:
                self.slider_ProgressBar.setValue(1000)
            else:
                self.slider_ProgressBar.setValue(progress)
        # 字幕更新
        if not subtitle == self.label_Subtitle.text():
            self.label_Subtitle.setText(subtitle)
        # 屏幕更新
        pixmap = QPixmap()
        if pixmap.load(pixmap_path):
            self.label_Screen.setPixmap(QPixmap(pixmap_path))  # 此语句可能造成程序异常退出

    '''
    def savePlaybackProgress(self):
        """ 存储播放进度 """
        if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
            file = open(SAVE_FILE_PATH + 'save.txt', 'w')
            file.write('%s\n%s\n' % (self.filename, self.frame_number))
            file.close()

    def loadPlaybackProgress(self):
        """ 加载播放进度 """
        # READY|PLAYING|PAUSING -- 发送停止命令
        if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
            self.sendRtspRequest(self.TEARDOWN)
        while not self.state == self.INIT:
            time.sleep(0.1)
        # 发送加载命令
        try:
            file = open(SAVE_FILE_PATH + 'save.txt', 'r')
            filename = file.readline()
            frame_number = file.readline()
        except FileNotFoundError:
            return False
        if not filename or not frame_number:
            return False
        self.filename = filename
        self.sendRtspRequest(self.SETUP)
        while not self.state == self.READY:
            time.sleep(0.1)
        self.frame_number = frame_number
        self.sendRtspRequest(self.PLAY)
        return True
    '''

    def keyPressEvent(self, event):
        """ GUI 键盘事件处理 """
        if event.key() == Qt.Key_Escape:
            self.sendRtspRequest(self.PAUSE)
            self.label_Screen.setPixmap(QPixmap(''))  # 重要 有效防止全屏切换时程序异常退出
            self.label_Screen.setWindowFlags(Qt.SubWindow)
            self.label_Screen.setGeometry(0, 50, 1024, 576)
            self.label_Subtitle.setGeometry(0, 495, 1024, 81)
            self.label_Screen.showNormal()
            self.sendRtspRequest(self.PLAY)

    def closeEvent(self, event):
        """ GUI 关闭事件处理 """
        # 关闭 RTSP 连接
        self.rtsp_socket.shutdown(socket.SHUT_RDWR)
        self.rtsp_socket.close()

    def __describe(self):
        """ 客户端进行 DESCRIBE 操作 """
        try:
            # 获取播放列表
            self.play_list = eval(self.rtsp_reply['List'])
            # 更新 GUI 播放列表
            self.listWidget_PlayList.clear()
            self.listWidget_PlayList.addItems(self.play_list)
            return True
        except KeyError:
            return False
        except OSError:
            return False
        except RuntimeError:
            return False

    def __setup(self):
        """ 客户端进行 SETUP 操作 """
        try:
            # INIT -- 加载视频
            if self.state == self.INIT:
                # 建立会话
                self.session_id = self.rtsp_reply['Session']
                self.frame_count = float(self.rtsp_reply['Length'])
                self.frame_number = 0
                # 建立 RTP 连接 -- 连接的建立移到发送指令时
                self.rtp_server_port = int(self.rtsp_reply['server_port'])
                self.rtp_play_event.clear()
                self.rtp_teardown_flag = False
                self.rtp_thread = threading.Thread(target=self.handleRtpConnection)
                self.rtp_thread.start()
                # 变量初始化
                self.subtitle = ''
                # 更新状态
                self.state = self.READY
                return True
            # READY|PLAYING|PAUSING -- 抛出异常
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                return False
        except KeyError:
            return False
        except OSError:
            return False
        except RuntimeError:
            return False

    def __play(self):
        """ 客户端进行 PLAY 操作 """
        try:
            # INIT -- 抛出异常
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 开始播放|继续播放|恢复播放
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 清空数据缓存
                self.rtp_data_buffer.clear()
                # 设置播放事件
                self.rtp_play_event.set()
                # 更新状态
                self.state = self.PLAYING
                return True
        except KeyError:
            return False
        except OSError:
            return False
        except RuntimeError:
            return False

    def __pause(self):
        """ 客户端进行 pause 操作 """
        try:
            # INIT|READY|PAUSING -- 抛出异常
            if self.state == self.INIT or self.state == self.READY or self.state == self.PAUSING:
                return False
            # PLAYING -- 暂停播放
            if self.state == self.PLAYING:
                # 设置播放事件
                self.rtp_play_event.clear()
                # 更新状态
                self.state = self.PAUSING
                return True
        except KeyError:
            return False
        except OSError:
            return False
        except RuntimeError:
            return False

    def __teardown(self):
        """ 客户端进行 teardown 操作 """
        try:
            # INIT -- 抛出异常
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 停止播放
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 设置 RTP 线程关闭标识
                self.rtp_teardown_flag = True
                # 设置播放事件  防止线程阻塞无法关闭
                self.rtp_play_event.set()
                # 关闭 RTP 套接字
                try:
                    self.rtp_socket.shutdown(socket.SHUT_RDWR)
                    self.rtp_socket.close()
                except AttributeError:
                    pass
                self.rtp_socket = None
                # 清除缓存
                try:
                    os.remove(CACHE_FILE_PATH + CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT)
                except FileNotFoundError:
                    pass
                # 关闭会话
                self.session_id = '0'
                self.filename = ''
                self.frame_count = 0
                self.frame_number = 0
                # 更新状态
                self.state = self.INIT
                return True
        except KeyError:
            return False
        except OSError:
            return False
        except RuntimeError:
            return False

    def __onFullScreenClicked(self):
        """ 槽 按下全屏按钮 """
        self.sendRtspRequest(self.PAUSE)
        self.label_Screen.setPixmap(QPixmap(''))  # 重要 有效防止全屏切换时程序异常退出
        self.label_Screen.setWindowFlag(Qt.Window)
        self.label_Screen.showFullScreen()
        self.label_Subtitle.setGeometry((self.label_Screen.width() - 1024) / 2, self.label_Screen.height() - 150, 1024, 81)
        self.sendRtspRequest(self.PLAY)

    def __onPlayPauseClicked(self):
        """ 槽 按下播放/暂停按钮 """
        # INIT|READY|PAUSING -- 播放按钮按下
        if self.state == self.INIT or self.state == self.READY or self.state == self.PAUSING:
            if self.state == self.READY or self.state == self.PAUSING:
                self.sendRtspRequest(self.PLAY)
        # PLAYING -- 暂停按钮按下
        elif self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def __onStopClicked(self):
        """ 槽 按下停止按钮 """
        # INIT -- 拒绝
        if self.state == self.INIT:
            return
        # READY|PLAYING|PAUSING -- 发送停止命令
        elif self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
            self.sendRtspRequest(self.TEARDOWN)

    def __onSubtitleClicked(self):
        """ 槽 按下字幕按钮 """
        if self.subtitle_mode:
            self.subtitle_mode = False
            self.pushButton_Subtitle.setStyleSheet('QPushButton{border-image: url(./img/subtitle.png)}')
        else:
            self.subtitle_mode = True
            self.pushButton_Subtitle.setStyleSheet('QPushButton{border-image: url(./img/subtitle_1.png)}')
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            self.sendRtspRequest(self.PLAY)

    def __onCompressClicked(self):
        """ 槽 按下压缩按钮 """
        if self.compress_mode:
            self.compress_mode = False
            self.pushButton_Compress.setStyleSheet('QPushButton{border-image: url(./img/compress.png)}')
        else:
            self.compress_mode = True
            self.pushButton_Compress.setStyleSheet('QPushButton{border-image: url(./img/compress_1.png)}')
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            self.sendRtspRequest(self.PLAY)

    def __onSearchClicked(self):
        """ 槽 按下搜索按钮 """
        keyword = self.lineEdit_Search.text()
        play_list = []
        for item in self.play_list:
            if keyword in item:
                play_list.append(item)
        self.listWidget_PlayList.clear()
        self.listWidget_PlayList.addItems(play_list)

    def __onPlaybackRateChanged(self):
        """ 槽 播放速度改变 """
        index = self.comboBox_PlaybackRate.currentIndex()
        if index == 0:
            self.frame_speed = 1.0
        elif index == 1:
            self.frame_speed = 0.5
        elif index == 2:
            self.frame_speed = 0.75
        elif index == 3:
            self.frame_speed = 1.25
        elif index == 4:
            self.frame_speed = 1.5
        elif index == 5:
            self.frame_speed = 2.0
        else:
            self.frame_speed = 1.0
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            self.sendRtspRequest(self.PLAY)

    def __onSubtitleAdjustChanged(self):
        """ 槽 音轨调节改变 """
        index = self.comboBox_SubtitleAdjust.currentIndex()
        if index == 0:
            self.subtitle_adjust = 0
        elif index == 1:
            self.subtitle_adjust = 0.2
        elif index == 2:
            self.subtitle_adjust = 0.5
        elif index == 3:
            self.subtitle_adjust = 1.0
        elif index == 4:
            self.subtitle_adjust = 2.0
        elif index == 5:
            self.subtitle_adjust = -0.2
        elif index == 6:
            self.subtitle_adjust = -0.5
        elif index == 7:
            self.subtitle_adjust = -1.0
        elif index == 8:
            self.subtitle_adjust = -2.0
        else:
            self.subtitle_adjust = 0
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            self.sendRtspRequest(self.PLAY)

    def __onProgressBarPressed(self):
        """ 槽 播放进度条选中"""
        # PLAYING -- 暂停
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def __onProgressBarReleased(self):
        """ 槽 播放进度条释放 """
        # INIT|READY -- 锁定为 0
        if self.state == self.INIT or self.state == self.READY:
            self.slider_ProgressBar.setValue(0)
        elif self.state == self.PLAYING or self.state == self.PAUSING:
            self.frame_number = round(self.slider_ProgressBar.value() / self.slider_ProgressBar.maximum() * self.frame_count)
            self.sendRtspRequest(self.PLAY)

    def __onListWidgetClicked(self, item):
        """ 槽 播放列表选择 """
        self.filename = item.text()
        self.sendRtspRequest(self.SETUP)

    '''
    def exitClient(self):
        """ Teardown button handler. """
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()  # Close the gui window
        try:
            os.remove(CACHE_FILE_PATH + CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT)  # Delete the cache image from video
        except OSError:
            pass
    '''


def main(argv):
    """ 程序主入口 """
    ip = SERVER_ADDR
    port = SERVER_PORT
    try:
        opts, args = getopt.getopt(argv, 'ip', ['ip=', 'port='])
    except getopt.GetoptError:
        print('usage: Client.py --ip <ip> --port <port>')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-i', '--ip'):
            ip = arg
        if opt in ('-p', '--port'):
            port = int(arg)
    # 创建图形界面
    app = QApplication(sys.argv)
    client = Client(ip, port)
    client.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main(sys.argv[1:])
