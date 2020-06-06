from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket
import threading
import sys
import traceback
import os
import random

from RtpPacket import RtpPacket

DISPLAY_MODE = True
SERVER_ADDR = '127.0.0.1'
SERVER_PORT = 9999
RTP_MIN_PORT = 5000
RTP_MAX_PORT = 10000
RTP_PACKET_MAX_SIZE = 102400

CACHE_FILE_PATH = './cache/'
CACHE_FILE_NAME = 'cache-'
CACHE_FILE_EXT = '.jpg'


class Client:
    """ 客户端类 """
    # 客户端状态宏定义
    INIT = 0        # 初始化
    READY = 1       # 准备就绪
    PLAYING = 2     # 正在播放
    PAUSING = 3     # 正在暂停
    # RTSP 命令宏定义
    NONE = -1       # NONE 命令
    LIST = 0        # LIST 命令
    SETUP = 1       # SETUP 命令
    PLAY = 2        # PLAY 命令
    PAUSE = 3       # PAUSE 命令
    TEARDOWN = 4    # TEARDOWN 命令

    # Initiation..
    def __init__(self, master, server_addr, server_port, filename):
        """ 类构造方法 """
        # --- GUI 初始化 ---
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        # --- RTSP/TCP 初始化 ---
        self.server_addr = server_addr           # 服务端 地址
        self.server_port = int(server_port)      # 服务端 端口
        self.rtsp_socket = None                  # RTSP/TCP 套接字
        self.rtsp_seq = 0                        # RTSP/TCP 请求序列号
        self.rtsp_request = ''                   # RTSP/TCP 请求（字符串）
        self.rtsp_request_code = self.NONE       # RTSP/TCP 请求代码
        self.rtsp_reply = {}                     # RTSP/TCP 回复（字典）
        self.session_id = '0'                    # RTSP/TCP 会话标识
        # --- RTP/UDP 初始化 ---
        self.rtp_server_port = 0                 # RTP/UDP 服务端端口
        self.rtp_client_port = 0                 # RTP/UDP 客户端端口
        self.rtp_socket = None                   # RTP/UDP 套接字
        self.rtp_thread = None                   # RTP/UDP 当前线程
        self.rtp_play_event = threading.Event()  # RTP/UDP 播放事件
        self.rtp_teardown_flag = False           # RTP/UDP 线程关闭标识
        self.filename = filename                 # 文件名（URL）
        self.frame_number = 0                    # 当前帧序号
        # --- 客户端 初始化 ---
        self.state = self.INIT                   # 客户端 初始状态
        # 连接到客户端
        if not self.createRtspConnection():
            # TODO 错误提示整合
            tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' % self.server_addr)

    def __list(self):
        """ 客户端进行 LIST 操作 """
        try:
            return True
        except KeyError or OSError or RuntimeError:
            return False

    def __setup(self):
        """ 客户端进行 SETUP 操作 """
        try:
            # INIT -- 加载视频
            if self.state == self.INIT:
                # 初始化
                self.frame_number = 0
                # 建立会话
                self.session_id = self.rtsp_reply['Session']
                # 建立 RTP 连接 -- 连接的建立移到发送指令时
                self.rtp_server_port = int(self.rtsp_reply['server_port'])
                self.rtp_play_event.clear()
                self.rtp_teardown_flag = False
                self.rtp_thread = threading.Thread(target=self.handleRtpConnection)
                self.rtp_thread.start()
                # 更新状态
                self.state = self.READY
                return True
            # READY|PLAYING|PAUSING -- 抛出异常
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                return False
        except KeyError or OSError or RuntimeError:
            return False

    def __play(self):
        """ 客户端进行 PLAY 操作 """
        try:
            # INIT -- 抛出异常
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 开始播放|继续播放|恢复播放
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 设置播放事件
                self.rtp_play_event.set()
                # 更新状态
                self.state = self.PLAYING
                return True
        except KeyError or OSError or RuntimeError:
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
        except KeyError or OSError or RuntimeError:
            return False

    def __teardown(self):
        """ 客户端进行 teardown 操作 """
        try:
            # INIT -- 抛出异常
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 停止播放
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 关闭会话
                self.session_id = '0'
                # 关闭 RTP 套接字
                self.rtp_socket.shutdown(socket.SHUT_RDWR)
                self.rtp_socket.close()
                self.rtp_socket = None
                # 设置 RTP 线程关闭标识
                self.rtp_teardown_flag = True
                # 设置播放事件  防止线程阻塞无法关闭
                self.rtp_play_event.set()
                # 更新状态
                self.state = self.INIT
                return True
        except KeyError or OSError or RuntimeError:
            return False

    def createRtspConnection(self):
        """ 创建 RTSP/TCP 连接 """
        if self.rtsp_socket:
            self.rtsp_socket.shutdown(socket.SHUT_RDWR)
            self.rtsp_socket.close()
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtsp_socket.connect((self.server_addr, self.server_port))
            threading.Thread(target=self.recvRtspReply).start()     # 派生线程  持续接收RTSP回复
            return True
        except:
            return False

    def sendRtspRequest(self, requestCode):
        """ 发送 RTSP/TCP 请求 """
        # SETUP 命令
        if requestCode == self.SETUP:
            if not self.state == self.INIT:
                return False
            while not self.createRtpConnection():   # 建立 RTP 连接
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
            self.rtsp_request = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
            self.rtsp_request_code = self.PLAY
        # PAUSE 命令
        elif requestCode == self.PAUSE:
            if not self.state == self.PLAYING:
                return False
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
            reply = self.rtsp_socket.recv(1024)
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
                if (not self.rtsp_request_code == self.SETUP) and (not self.rtsp_request_code == self.TEARDOWN) and (not self.session_id == self.rtsp_reply['Session']):
                    raise KeyError
                # LIST 命令
                if self.rtsp_request_code == self.LIST:
                    if not self.__list():
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
            except KeyError:
                print('客户端回复格式错误')
            except NotImplementedError:
                print('未实现命令')
            except RuntimeError:
                print('命令执行错误')
        # 关闭连接套接字
        self.rtsp_socket.shutdown(socket.SHUT_RDWR)
        self.rtsp_socket.close()

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
        try:
            # 绑定套接字  使用随机的端口
            self.rtp_client_port = random.randint(RTP_MIN_PORT, RTP_MAX_PORT)
            self.rtp_socket.bind(("", self.rtp_client_port))
            return True
        except OSError:
            # TODO 错误处理
            tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' % self.rtp_client_port)
            self.rtp_socket = None
            return False

    def handleRtpConnection(self):
        """ 处理 RTP/UDP 连接 """
        # TODO
        while True:
            try:
                self.rtp_play_event.wait()
                if self.rtp_teardown_flag:
                    raise OSError
                data, addr = self.rtp_socket.recvfrom(RTP_PACKET_MAX_SIZE)
                if data:
                    rtp_packet = RtpPacket()
                    rtp_packet.decode(data)
                    current_frame_number = rtp_packet.seqnum()
                    print('@ ' + str(current_frame_number))

                    if current_frame_number > self.frame_number:
                        self.frame_number = current_frame_number
                        self.updateMovie(self.writeFrame(rtp_packet.get_payload()))
            except OSError:
                break
        print('@ 客户端线程已退出')


    def createWidgets(self):
        """ 创建客户端 GUI """
        # Create Setup button
        self.setup = Button(self.master, width=20, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

    def setupMovie(self):
        """ Setup button handler. """
        self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """ Teardown button handler. """
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()  # Close the gui window
        try:
            os.remove(CACHE_FILE_PATH + CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT)  # Delete the cache image from video
        except OSError:
            pass

    def pauseMovie(self):
        """Pause button handler."""
        self.sendRtspRequest(self.PAUSE)
        return

    def playMovie(self):
        """Play button handler."""
        self.sendRtspRequest(self.PLAY)

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_PATH + CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT
        while True:
            try:
                file = open(cachename, "wb")
                file.write(data)
                file.close()
            except OSError or PermissionError:
                continue
            break
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=288)
        self.label.image = photo

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()


def main():
    root = Tk()
    client = Client(root, '127.0.0.1', SERVER_PORT, "")
    root.mainloop()


if __name__ == '__main__':
    main()
