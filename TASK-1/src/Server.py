import os
import sys
import socket
import threading
import time
import re
import random
from RtpPacket import RtpPacket

DISPLAY_MODE = True
SERVER_ADDR = '127.0.0.1'
SERVER_PORT = 9999
SERVER_MAX_CONNECTION = 10
RTP_MIN_PORT = 5000
RTP_MAX_PORT = 10000
MIN_SESSION_ID = 10000000
MAX_SESSION_ID = 99999999

RTP_FRAME = 10
RTP_INTERVAL = 1 / RTP_FRAME


used_session_id_list = set()


class Handler:
    """ 处理器类 """
    # 客户端状态宏定义
    INIT = 0  # 初始化
    READY = 1  # 准备就绪
    PLAYING = 2  # 正在播放
    PAUSING = 3  # 正在暂停

    def __init__(self, rtsp_socket, client_addr):
        """ 类构造方法 """
        # --- RTSP/TCP 初始化 ---
        self.client_addr = client_addr           # 客户端 地址（与端口）
        self.rtsp_socket = rtsp_socket           # RTSP/TCP 套接字
        self.rtsp_request = {}                   # RTSP/TCP 请求（字典）
        self.rtsp_reply = ''                     # RTSP/TCP 回复（字符串）
        self.session_id = '0'                    # RTSP/TCP 会话标识
        # --- RTP/UDP 初始化 ---
        self.rtp_server_port = 0                 # RTP/UDP 服务端端口
        self.rtp_client_port = 0                 # RTP/UDP 客户端端口
        self.rtp_socket = None                   # RTP/UDP 套接字
        self.rtp_thread = None                   # RTP/UDP 当前线程
        self.rtp_play_event = threading.Event()  # RTP/UDP 播放事件
        self.rtp_teardown_flag = False           # RTP/UDP 线程关闭标识
        self.filename = ''                       # 文件名（URL）
        self.frame_number = 0                    # 当前帧序号
        # --- 服务端 初始化 ---
        self.state = self.INIT  # 服务端 初始状态

    def __list(self):
        """ 服务端进行 LIST 操作 """
        try:
            return True
        except KeyError or OSError or RuntimeError:
            return False

    def __setup(self):
        """ 服务端进行 SETUP 操作 """
        try:
            # INIT -- 加载资源
            if self.state == self.INIT:
                # 资源初始化 TODO
                self.filename = self.rtsp_request['URL']
                self.frame_number = 0
                # 建立会话
                while True:
                    # 生成随机 session_id
                    self.session_id = str(random.randint(MIN_SESSION_ID, MAX_SESSION_ID))
                    if self.session_id not in used_session_id_list:
                        used_session_id_list.add(self.session_id)
                        break
                # 建立 RTP 连接
                self.rtp_client_port = int(self.rtsp_request['client_port'])
                while not self.createRtpConnection():
                    pass
                self.rtp_play_event.clear()
                self.rtp_teardown_flag = False
                self.rtp_thread = threading.Thread(target=self.handleRtpConnection)
                self.rtp_thread.start()
                # 更新状态
                self.state = self.READY
                return True
            # READY|PLAYING|PAUSING -- 拒绝
            if self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                return False
        except KeyError or OSError or RuntimeError:
            return False

    def __play(self):
        """  服务端进行 PLAY 操作 """
        try:
            # INIT -- 拒绝
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 开始播放|继续播放|恢复播放
            elif self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 开始播放
                if self.state == self.READY:
                    pass    # TODO
                # 继续播放
                elif self.state == self.PLAYING:
                    pass    # TODO
                # 恢复播放
                elif self.state == self.PAUSING:
                    pass    # TODO
                # 设置播放事件
                self.rtp_play_event.set()
                # 更新状态
                self.state = self.PLAYING
                return True
        except KeyError or OSError or RuntimeError:
            return False

    def __pause(self):
        """ 服务端进行 pause 操作 """
        try:
            # INIT|READY|PAUSING -- 拒绝
            if self.state == self.INIT or self.state == self.READY or self.state == self.PAUSING:
                return False
            # PLAYING --暂停播放
            elif self.state == self.PLAYING:
                # 设置播放事件
                self.rtp_play_event.clear()
                # 更新状态
                self.state = self.PAUSING
                return True
        except KeyError or OSError or RuntimeError:
            return False

    def __teardown(self):
        """ 服务端进行 teardown 操作 """
        try:
            # INIT -- 拒绝
            if self.state == self.INIT:
                return False
            # READY|PLAYING|PAUSING -- 停止播放
            elif self.state == self.READY or self.state == self.PLAYING or self.state == self.PAUSING:
                # 关闭会话
                if self.session_id in used_session_id_list:
                    used_session_id_list.remove(self.session_id)
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
        # except KeyError or OSError or RuntimeError:
        except RuntimeError:

            return False

    def handleRtspConnection(self):
        """ 处理 RTSP/TCP 连接 """
        # 进行请求处理循环
        while True:
            # *** 接收 RTSP/TCP 请求  recvRtspRequest ***
            request = self.rtsp_socket.recv(1024)
            if not request:
                break
            data = request.decode('utf-8')
            if DISPLAY_MODE:
                print('\n@ Data recv:\n' + data)
                print('\n@ Original state: ' + str(self.state))

            # *** 处理 RTSP/TCP 请求  handleRtspRequest ***
            try:
                # 分析 RTSP/TCP 请求
                if not self.parseRtspRequest(data):
                    raise KeyError
                # session_id 判断
                if (not self.rtsp_request['Command'] == 'SETUP') and (not self.session_id == self.rtsp_request['Session']):
                    raise KeyError
                # LIST 命令
                if self.rtsp_request['Command'] == 'LIST':
                    if self.__list():
                        # 返回 200  TODO
                        line_1 = ['RTSP/1.0', '200', 'OK']
                        line_2 = ['CSeq:', self.rtsp_request['CSeq']]
                        line_3 = ['Session:', self.session_id]
                        self.rtsp_reply = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
                    else:
                        # 返回 400
                        self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
                # SETUP 命令
                if self.rtsp_request['Command'] == 'SETUP':
                    if self.__setup():
                        # 返回 200
                        line_1 = ['RTSP/1.0', '200', 'OK']
                        line_2 = ['CSeq:', self.rtsp_request['CSeq']]
                        line_3 = ['Transport:', 'RTP/UDP;client_port=' + str(self.rtsp_request['client_port']) + ';server_port=' + str(self.rtp_server_port) + ';ssrc=']
                        line_4 = ['Session:', self.session_id]
                        self.rtsp_reply = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n' + ' '.join(line_4) + '\n'
                    else:
                        # 返回 400
                        self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
                # PLAY 命令
                elif self.rtsp_request['Command'] == 'PLAY':
                    if self.__play():
                        # 返回 200
                        line_1 = ['RTSP/1.0', '200', 'OK']
                        line_2 = ['CSeq:', self.rtsp_request['CSeq']]
                        line_3 = ['Session:', self.session_id]
                        self.rtsp_reply = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
                    else:
                        # 返回 400
                        self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
                # PAUSE 命令
                elif self.rtsp_request['Command'] == 'PAUSE':
                    if self.__pause():
                        # 返回 200
                        line_1 = ['RTSP/1.0', '200', 'OK']
                        line_2 = ['CSeq:', self.rtsp_request['CSeq']]
                        line_3 = ['Session:', self.session_id]
                        self.rtsp_reply = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n' + ' '.join(line_3) + '\n'
                    else:
                        # 返回 400
                        self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
                # TEARDOWN 命令
                elif self.rtsp_request['Command'] == 'TEARDOWN':
                    if self.__teardown():
                        # 返回 200
                        line_1 = ['RTSP/1.0', '200', 'OK']
                        line_2 = ['CSeq:', self.rtsp_request['CSeq']]
                        self.rtsp_reply = ' '.join(line_1) + '\n' + ' '.join(line_2) + '\n'
                    else:
                        # 返回 400
                        self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
                # 其他命令
                else:
                    raise NotImplementedError
                if DISPLAY_MODE:
                    print('\n@ Current state: ' + str(self.state))
            except KeyError:
                # 请求格式错误 400
                self.rtsp_reply = 'RTSP/1.0 400 Bad Request\n'
            except NotImplementedError:
                # 方法不支持错误 405
                self.rtsp_reply = 'RTSP/1.0 405 Method Not Allowed\n'
            # 发送 RTSP/TCP 回复  sendRtspReply
            self.rtsp_socket.send(self.rtsp_reply.encode())
        # 关闭连接套接字
        self.rtsp_socket.shutdown(socket.SHUT_RDWR)
        self.rtsp_socket.close()

    def parseRtspRequest(self, data):
        """ 分析 RTSP/TCP 请求 """
        try:
            # 创建参数字典
            lines = str(data).split('\n')
            self.rtsp_request = {'Command': lines[0].split(' ')[0], 'URL': lines[0].split(' ')[1], 'CSeq': lines[1].split(' ')[1]}
            # 字段信息提取
            for line in lines[1:]:
                words = line.split(' ')
                # 提取 Session
                if 'Session' in words[0]:
                    self.rtsp_request['Session'] = words[1]
                # 提取 Transport
                elif 'Transport' in words[0]:
                    # 提取 client_port
                    pattern = re.compile(r'client_port=\s*(\S*?)\s*(;|$)')
                    result = pattern.search(line)
                    if result:
                        self.rtsp_request['client_port'] = result.group(1)
                    else:
                        raise KeyError
                # 提取 Range
                elif 'Range' in words[0]:
                    pass
            return True
        except KeyError:
            self.rtsp_request = {}
            return False

    def createRtpConnection(self):
        """ 创建 RTP/UDP 连接 """
        # 创建 RTP/UDP 套接字
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 绑定套接字  使用随机的端口
            self.rtp_server_port = random.randint(RTP_MIN_PORT, RTP_MAX_PORT)
            self.rtp_socket.bind(("", self.rtp_server_port))
            return True
        except OSError:
            self.rtp_socket = None
            return False

    def handleRtpConnection(self):
        """ 处理 RTP/UDP 连接 """
        # TODO
        while True:
            try:
                time.sleep(RTP_INTERVAL)
                self.rtp_play_event.wait()
                if self.rtp_teardown_flag:
                    raise OSError
                self.frame_number += 1
                pic_index = self.frame_number % 183
                pic_path = './pic/pic-%05d.jpg' % pic_index
                self.rtp_socket.sendto(self.createRtpPacket(pic_path).get_packet(), ('127.0.0.1', self.rtp_client_port))
            except OSError:
                break
        print('@ 服务端线程已退出')

    def createRtpPacket(self, path):
        file = open(path, "rb")
        data = file.read()
        file.close()
        rtp_packet = RtpPacket()
        rtp_packet.encode(0, 0, 0, 0, 0, 0, self.frame_number, 0, data)
        return rtp_packet

class Server:
    """ 服务端类 """

    def __init__(self, server_addr, server_port, server_max_connection):
        """ 类构造方法 """
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.bind((server_addr, server_port))
        self.rtspSocket.listen(server_max_connection)
        if DISPLAY_MODE:
            print('Server initialization succeeded.\nWaiting for connection...')

    def run(self):
        """ 创建 RTSP/TCP 连接（循环阻塞） """
        while True:
            # 接受新RTSP连接:
            sock, addr = self.rtspSocket.accept()
            # 多线程  处理RTSP连接
            t = threading.Thread(target=self.handle, args=(sock, addr))
            t.start()

    @staticmethod
    def handle(sock, addr):
        """ 处理 RTSP/TCP 连接 """
        if DISPLAY_MODE:
            print('Accept new connection from %s:%s...' % addr)
        handler = Handler(sock, addr)
        handler.handleRtspConnection()
        if DISPLAY_MODE:
            print('Connection from %s:%s closed.' % addr)


if __name__ == '__main__':
    server = Server(SERVER_ADDR, SERVER_PORT, SERVER_MAX_CONNECTION)
    server.run()
