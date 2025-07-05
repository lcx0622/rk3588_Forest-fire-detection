# main_ui.py
import sys
import os
import numpy as np
from pathlib import Path
import multiprocessing as mp

# ==================== 绝对不能有 import cv2 或 import zmq ====================

from PySide6.QtCore import QObject, Signal, Slot, QThread, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider


# --- 图像提供者 (完全不变) ---
class LiveImageProvider(QQuickImageProvider):
    imageChanged = Signal()

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.current_image = QImage()

    def requestImage(self, id, size, requestedSize):
        return self.current_image

    @Slot(QImage)
    def update_image(self, new_image):
        if not new_image.isNull():
            self.current_image = new_image
            self.imageChanged.emit()


# --- 帧读取器 (从 multiprocessing.Queue 读取) ---
class FrameReader(QObject):
    frameReady = Signal(QImage)

    def __init__(self, frame_queue, parent=None):
        super().__init__(parent)
        self.queue = frame_queue
        self.running = False

    @Slot()
    def start(self):
        self.running = True
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_frame_from_queue)
        self.timer.start(16)  # ~60 FPS
        print("[UI Process] FrameReader started.")

    @Slot()
    def stop(self):
        self.running = False
        if self.timer:
            self.timer.stop()

    def read_frame_from_queue(self):
        if not self.running or self.queue.empty():
            return

        # 从队列获取 Numpy 数组 (BGR格式)
        bgr_frame = self.queue.get()
        # 先打印图像信息，确保我们拿到的是正确的格式
        print(
            f"[UI Process] Received frame: shape={bgr_frame.shape}, dtype={bgr_frame.dtype}"
        )
        # 打印图像中的最大值，确保数据正常
        print(f"[UI Process] Frame max value: {np.max(bgr_frame)}")

        # ================================================================
        # 在这个“纯净”的UI进程中，我们唯一需要做的就是将BGR字节流转换为QImage
        # 这里甚至不需要 OpenCV 的 cvtColor，可以直接创建
        # 注意：Numpy 数组的 data 是一个内存视图，直接传递给 QImage 是最高效的
        # ================================================================
        h, w, ch = bgr_frame.shape
        if ch == 3:  # BGR
            qt_image = QImage(bgr_frame.data, w, h, w * ch, QImage.Format.Format_BGR888)
            self.frameReady.emit(qt_image.copy())


if __name__ == "__main__":
    # 必须在开头设置，以确保多进程能正确启动
    # 'spawn' 是最干净的启动方式，子进程不会继承父进程的内存
    mp.set_start_method("spawn", force=True)

    # 这是你确认能工作的设置
    os.environ["QT_QUICK_BACKEND"] = "rhi"

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    # 1. 创建进程间通信队列
    frame_queue = mp.Queue(maxsize=50)

    # 2. 延迟导入并启动工作进程
    def start_worker_process(queue):
        from worker_process import worker_loop  # 只有在这里才 import

        process = mp.Process(target=worker_loop, args=(queue,))
        process.daemon = True
        process.start()
        print(f"[UI Process] Worker process started with PID: {process.pid}")
        return process

    worker_process = start_worker_process(frame_queue)

    # 3. 设置UI部分
    image_provider = LiveImageProvider()
    engine.addImageProvider("livevideo", image_provider)
    engine.rootContext().setContextProperty("imageProvider", image_provider)

    # 4. 创建并启动帧读取线程
    reader_thread = QThread()
    frame_reader = FrameReader(frame_queue)
    frame_reader.moveToThread(reader_thread)
    reader_thread.started.connect(frame_reader.start)
    frame_reader.frameReady.connect(
        image_provider.update_image, Qt.ConnectionType.QueuedConnection
    )

    # 5. 设置清理逻辑
    def cleanup():
        print("[UI Process] Cleaning up...")
        frame_reader.stop()
        reader_thread.quit()
        reader_thread.wait()
        if worker_process.is_alive():
            worker_process.terminate()
            worker_process.join()
        print("[UI Process] Cleanup complete.")

    app.aboutToQuit.connect(cleanup)

    # 6. 加载QML并运行
    qml_file = Path(__file__).resolve().parent / "main.qml"  # 你的QML文件名
    engine.load(QUrl.fromLocalFile(qml_file))
    if not engine.rootObjects():
        sys.exit(-1)

    reader_thread.start()
    sys.exit(app.exec())
