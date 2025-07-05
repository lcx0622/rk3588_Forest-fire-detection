import cv2
import time
import os
from rknnpool import rknnPoolExecutor

# 图像处理函数，实际应用过程中需要自行修改
from func import myFunc

import zmq

# --- ZMQ 初始化 ---
print("Initializing ZeroMQ Publisher...")
context = zmq.Context()
socket = context.socket(zmq.PUB)
# 绑定到一个 TCP 端口。'5555' 是一个例子，你可以换成别的
# 使用 '*' 表示允许任何 IP 连接
socket.bind("tcp://*:5454")
print("ZMQ Publisher is ready on tcp://*:5454")
# --- 结束 ZMQ 初始化 ---

# 指定输出文件夹
output_folder = "/root/code/rknn3588-yolov8/output/output_videos1"
os.makedirs(output_folder, exist_ok=True)

cap = cv2.VideoCapture("./test.mp4")
# cap = cv2.VideoCapture(0)
# cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
# cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
# cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
# cap.set(cv2.CAP_PROP_FPS, 60)

modelPath = "./1_rknnModel/yolov8_seg.rknn"
# 线程数, 增大可提高帧率
TPEs = 3
# 初始化rknn池
pool = rknnPoolExecutor(rknnModel=modelPath, TPEs=TPEs, func=myFunc)

# 初始化异步所需要的帧
if cap.isOpened():
    for i in range(TPEs + 1):
        ret, frame = cap.read()
        if not ret:
            cap.release()
            del pool
            exit(-1)
        pool.put(frame)

frames, loopTime, initTime = 0, time.time(), time.time()

# 获取视频信息
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

# # 创建视频写入对象
# output_path = os.path.join(output_folder, "output_video.mp4")
# fourcc = cv2.VideoWriter_fourcc(*"mp4v")
# out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

while cap.isOpened():
    frames += 1
    ret, frame = cap.read()
    if not ret:
        break
    # print(frame.shape)
    pool.put(frame)
    processed_frame, flag = pool.get()
    if flag == False:
        break
    # print(frame.shape)
    # ==================== 核心修改：发送图像而不是显示 ====================

    # 将图像编码为JPEG格式，以减少传输数据量
    # 95 是质量参数 (0-100)，越高图像质量越好，数据量越大
    _, buffer = cv2.imencode(".jpg", processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

    # ZMQ 发送编码后的数据
    socket.send(buffer)

    # 你可以加一个小的延时来控制发送帧率，如果需要的话
    # time.sleep(0.01)

    # ========================================================================
    # cv2.imshow("yolov8", processed_frame)

    # # 将处理后的帧写入输出视频
    # out.write(processed_frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
    if frames % 30 == 0:
        print("30帧平均帧率:\t", 30 / (time.time() - loopTime), "帧")
        loopTime = time.time()

print("总平均帧率\t", frames / (time.time() - initTime))
# 释放cap和rknn线程池
cap.release()
cv2.destroyAllWindows()
pool.release()
