# coding=utf-8
import sys
from time import time
HEADER_SIZE = 12


# =============================
# RtpPacket  RTP数据包类
# =============================
class RtpPacket:
    # header = bytearray(HEADER_SIZE)
    # payload = bytearray()

    def __init__(self):
        pass

    def __del__(self):
        pass

    def encode(self, version, padding, extension, cc, marker, pt, seqnum, ssrc, payload):
        """ Encode the RTP packet with header fields and payload. """
        timestamp = int(time())
        header = bytearray(HEADER_SIZE)
        # version -- 版本号 (2 bits)
        # padding -- 填充标识 (1 bit)
        # extension -- 调整标识 (1 bit)
        # cc -- CSRC计数器 (4 bits)
        # marker -- 标记 (1 bit)
        # pt -- 有效荷载类型 (7 bits)
        # seqnum -- 序列号 (16 bits)
        # timestamp -- 时间戳 (32 bits)
        # ssrc -- 同步信源(SSRC)标识符 (32 bits)
        # payload -- 有效载荷 (? bits)
        header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
        header[1] = (marker << 7) | pt
        header[2] = (seqnum >> 8) & 255
        header[3] = seqnum & 255
        header[4] = timestamp >> 24 & 255
        header[5] = timestamp >> 16 & 255
        header[6] = timestamp >> 8 & 255
        header[7] = timestamp & 255
        header[8] = ssrc >> 24 & 255
        header[9] = ssrc >> 16 & 255
        header[10] = ssrc >> 8 & 255
        header[11] = ssrc & 255
        self.header = header
        self.payload = payload
        return

    def decode(self, byteStream):
        """ Decode the RTP packet. """
        self.header = bytearray(byteStream[:HEADER_SIZE])
        self.payload = byteStream[HEADER_SIZE:]
        return

    def version(self):
        """ Return RTP version. """
        return int(self.header[0] >> 6)

    def seqnum(self):
        """ Return sequence (frame) number. """
        seqnum = self.header[2] << 8 | self.header[3]
        return int(seqnum)

    def timestamp(self):
        """ Return timestamp. """
        timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
        return int(timestamp)

    def payload_type(self):
        """ Return payload type. """
        pt = self.header[1] & 127
        return int(pt)

    def get_header(self):
        """ Return header. """
        return self.header

    def get_payload(self):
        """ Return payload. """
        return self.payload

    def get_packet(self):
        """Return RTP packet."""
        return self.header + self.payload
