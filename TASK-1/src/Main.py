import sys

from PyQt5.QtWidgets import QApplication, QMainWindow
from Window import Ui_MainWindow


class Window(QMainWindow, Ui_MainWindow):
    def __init__(self):

        # 界面初始化
        super(Window, self).__init__()
        self.setupUi(self)
        self.setFixedSize(1280, 720)

        self.playback_rate_list = ['播放速度 <1.0>', '播放速度 <0.5>', '播放速度 <0.75>', '播放速度 <1.25>', '播放速度 <1.5>', '播放速度 <2.0>']
        self.track_adjust_list = ['音轨调节 <+0>', '音轨调节 <+0.2>', '音轨调节 <+0.5>',  '音轨调节 <+1.0>',  '音轨调节 <+2.0>',
                                  '音轨调节 <-0.2>', '音轨调节 <-0.5>', '音轨调节 <-1.0>', '音轨调节 <-2.0>']
        self.play_list = ['A', 'B', 'C', 'D', 'E', 'F']
        self.comboBox_PlaybackRate.addItems(self.playback_rate_list)
        self.comboBox_TrackAdjust.addItems(self.track_adjust_list)
        self.listWidget_PlayList.addItems(self.play_list)
        self.slider_ProgressBar.setValue(0)
        self.__updateInfoBar()
        # 信号槽绑定
        self.pushButton_FullScreen.clicked.connect(self.__onFullScreenClicked)
        self.pushButton_PlayPause.clicked.connect(self.__onPlayPauseClicked)
        self.pushButton_Stop.clicked.connect(self.__onStopClicked)
        self.pushButton_Subtitle.clicked.connect(self.__onSubtitleClicked)
        self.pushButton_Search.clicked.connect(self.__onSearchClicked)
        self.comboBox_PlaybackRate.currentIndexChanged.connect(self.__onPlaybackRateChanged)
        self.comboBox_TrackAdjust.currentIndexChanged.connect(self.__onTrackAdjustChanged)
        self.slider_ProgressBar.sliderReleased.connect(self.__onProgressBarChanged)
        self.listWidget_PlayList.itemDoubleClicked.connect(self.__onListWidgetClicked)
        # 变量定义
        self.isPlaying = False

    def __onFullScreenClicked(self):
        """ 槽 按下全屏按钮 """
        print('FullScreen')

    def __onPlayPauseClicked(self):
        """ 槽 按下播放/暂停按钮 """
        if self.isPlaying:
            self.isPlaying = False
            self.pushButton_PlayPause.setToolTip('播放')
            self.pushButton_PlayPause.setStyleSheet('QPushButton{border-image: url(img/play.png)}'
                                                    'QPushButton:hover{border-image: url(img/play_1.png)}'
                                                    'QPushButton:pressed{border-image: url(img/play_2.png)}')
        else:
            self.isPlaying = True
            self.pushButton_PlayPause.setToolTip('暂停')
            self.pushButton_PlayPause.setStyleSheet('QPushButton{border-image: url(img/pause.png)}'
                                                    'QPushButton:hover{border-image: url(img/pause_1.png)}'
                                                    'QPushButton:pressed{border-image: url(img/pause_2.png)}')

    def __onStopClicked(self):
        """ 槽 按下停止按钮 """
        # TODO
        print('Stop')

    def __onStopClicked(self):
        """ 槽 按下停止按钮 """
        # TODO
        print('Stop')

    def __onSubtitleClicked(self):
        """ 槽 按下字幕按钮 """
        # TODO
        print('Subtitle')

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
        # TODO
        print(self.comboBox_PlaybackRate.currentIndex())

    def __onTrackAdjustChanged(self):
        """ 槽 音轨调节改变 """
        # TODO
        print(self.comboBox_TrackAdjust.currentIndex())

    def __onProgressBarChanged(self):
        """ 槽 播放进度条改变 """
        # TODO
        print(self.slider_ProgressBar.value())

    def __onListWidgetClicked(self, item):
        """ 槽 播放列表选择 """
        # TODO
        print(item.text())

    def __updateInfoBar(self):
        """ 槽 更新信息栏 """
        self.label_Info.setText('准备就绪')


def main():
    """ 程序主入口 """
    # 创建图形界面
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
