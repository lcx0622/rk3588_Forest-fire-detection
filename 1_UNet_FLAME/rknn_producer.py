# main_unet_video.py
import cv2
import time
import os
import argparse
import zmq
import numpy as np

# 确保rknnpool.py在Python路径中，或者与此脚本在同一目录
from rknnpool import rknnPoolExecutor
from func_unet import myFunc  # 从 func_unet.py 导入我们修改过的 myFunc

# --- ZMQ 初始化 ---
print("Initializing ZeroMQ Publisher...")
context = zmq.Context()
socket = context.socket(zmq.PUB)
# 绑定到一个 TCP 端口。'5555' 是一个例子，你可以换成别的
# 使用 '*' 表示允许任何 IP 连接
socket.bind("tcp://*:5454")
print("ZMQ Publisher is ready on tcp://*:5454")
# --- 结束 ZMQ 初始化 ---

current_directory = os.getcwd()
print("Current Directory:", current_directory)

base_dir = os.path.dirname(os.path.abspath(__file__))
print("base_dir:", base_dir)

parser = argparse.ArgumentParser(
    description="UNet video segmentation with rknnPoolExecutor."
)
parser.add_argument(
    "--model_path",
    type=str,
    default="1_rknnModel/mIoU__UNetPP_FLAME__epoch_realitymasks_04.rknn",
    help="UNet RKNN model path",
)
parser.add_argument(
    "--video_path", type=str, default="2_video/test.mp4", help="Input video path"
)
parser.add_argument(
    "--output_path",
    type=str,
    default="3_output_video/mIoU__UNetPP_FLAME__epoch_realitymasks_04.mp4",
    help="Output video path",
)
parser.add_argument(
    "--target",
    type=str,
    default="rk3588",
    help="Target RKNPU platform (currently not used by rknnpool directly in this example)",
)
parser.add_argument(
    "--tpes",
    type=int,
    default=3,
    help="Number of Thread Pool Executors (inference threads)",
)
parser.add_argument(
    "--show", type=int, default=0, help="Show output frames (1 to show, 0 to not show)"
)

args = parser.parse_args()
print("Arguments:", vars(args))

input_video_path = os.path.join(base_dir, args.video_path)
model_rknn_path = os.path.join(base_dir, args.model_path)
output_video_path = os.path.join(base_dir, args.output_path)

# 打开视频捕获
# 摄像头设备索引，通常是 0。如果 /dev/video0 不存在或被占用，请尝试 1, 2, ...
CAMERA_DEVICE_INDEX = 21

cap = cv2.VideoCapture(input_video_path)
# cap = cv2.VideoCapture(
#     CAMERA_DEVICE_INDEX, cv2.CAP_V4L2
# )  # 如果 input_video_path 是一个数字（如0），它会尝试打开对应的摄像头
# cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
# cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
if not cap.isOpened():
    print(f"错误: 无法打开输入视频: {input_video_path}")
    exit(-1)

# 获取视频属性以用于 VideoWriter
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  # 获取视频帧的宽度。
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))  # 获取视频帧的高度。
fps = cap.get(cv2.CAP_PROP_FPS)  # 获取视频的帧率
print(f"输入视频属性: Width={frame_width}, Height={frame_height}, FPS={fps:.2f}")

# 初始化 rknnPoolExecutor
# TPEs 数量，增加可以提高帧率，但取决于NPU核心数和系统负载
TPEs = args.tpes
print(f"Initializing RKNN Pool with TPEs: {TPEs}")
pool = rknnPoolExecutor(
    rknnModel=model_rknn_path,  # 传递模型路径
    TPEs=TPEs,
    func=myFunc,  # 我们在 func_unet.py 中定义的回调函数
)
print("RKNN Pool initialized.")

# 初始化 VideoWriter
# 对于拼接后的视频，宽度会加倍
# 如果 myFunc 只返回掩码（与原图同尺寸），则用 frame_width
output_frame_width = frame_width  # 如果myFunc返回的是与原图同尺寸的掩码或叠加图
# output_frame_width = frame_width * 2 # 因为 myFunc 中 hstack 了两个图像
output_frame_height = frame_height

# 预先填充处理队列，以利用异步处理，先进行几帧的处理，等get的时候可以直接获取
print("Pre-filling the queue...")
for i in range(TPEs + 1):  # +1 确保至少有一个结果可以立即get
    ret, frame = cap.read()
    if not ret:
        print("Warning: Video ended before pre-filling queue completely.")
        break
    pool.put(frame)  # 将原始帧放入队列，myFunc会处理它
print(f"Pre-filled {i+1 if ret else i} frames.")


frames_processed_count = 0
loopTime = time.time()
initTime = time.time()
# ==================== 新增：用于实时显示和FPS计算的变量 ====================
fps_start_time = time.time()
fps_frame_count = 0
display_fps = 0.0
# ========================================================================

print("开始视频处理循环...")
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 关键修改：在提交前创建一个帧的副本！
        frame_copy = frame.copy()
        pool.put(frame_copy)

        # 3. 从处理池获取一个已经处理完成的结果
        # get() 是阻塞的, 它会等待直到 myFunc 返回一个结果
        result = pool.get()

        # 检查从线程池获取的结果是否有效
        if result is None:
            print("从处理池收到一个 None 结果，跳过此帧。")
            continue

        # 假设 myFunc 返回 (处理后的图像, 标志位)
        processed_frame_for_output, flag = result

        # 如果处理失败，可以选择跳过或显示原始帧
        if not flag:
            print("警告: 帧处理失败。")
            # 如果处理失败，我们依然可以显示原始输入帧以避免画面卡顿
            processed_frame_for_output = frame_copy

        # ==================== 核心修改：嵌入实时显示逻辑 ====================

        # --- 计算帧率 (FPS) ---
        fps_frame_count += 1
        # 每秒更新一次FPS显示值
        if time.time() - fps_start_time >= 1.0:
            display_fps = fps_frame_count / (time.time() - fps_start_time)
            fps_frame_count = 0
            fps_start_time = time.time()

        # --- 在处理后的图像上绘制信息 ---
        # 获取处理后图像的实际尺寸，因为myFunc可能改变了它
        output_height, output_width, _ = processed_frame_for_output.shape
        info_text_resolution = f"Output Res: {output_width} x {output_height}"
        info_text_fps = f"Display FPS: {display_fps:.2f}"

        # 使用 cv2.putText() 将文本绘制到帧上
        cv2.putText(
            processed_frame_for_output,
            info_text_resolution,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            processed_frame_for_output,
            info_text_fps,
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        # ==================== 核心修改：发送图像而不是显示 ====================

        # 将图像编码为JPEG格式，以减少传输数据量
        # 95 是质量参数 (0-100)，越高图像质量越好，数据量越大
        _, buffer = cv2.imencode(
            ".jpg", processed_frame_for_output, [cv2.IMWRITE_JPEG_QUALITY, 95]
        )

        # ZMQ 发送编码后的数据
        socket.send(buffer)

        # 你可以加一个小的延时来控制发送帧率，如果需要的话
        # time.sleep(0.01)

        # ========================================================================
except KeyboardInterrupt:
    print("检测到 Ctrl+C，正在关闭程序...")
finally:
    # --- 释放资源 ---
    print("正在等待所有处理任务完成...")
    pool.release()
    print("正在释放摄像头...")
    cap.release()
    print("正在关闭ZMQ...")
    socket.close()
    context.term()
    print("程序已成功关闭。")
