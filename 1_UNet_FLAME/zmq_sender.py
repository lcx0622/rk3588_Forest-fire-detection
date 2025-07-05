# image_sender.py
import cv2
import zmq
import time

# --- 配置 ---
IMAGE_PATH = "tmp69C.png"  # 要发送的图片文件路径
ZMQ_ADDRESS = "tcp://*:5454"  # 发布者绑定的地址，* 表示监听所有可用网络接口

# 1. 初始化 ZMQ 上下文和发布者套接字
print("正在初始化 ZMQ 发布者...")
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind(ZMQ_ADDRESS)
print(f"ZMQ 发布者已绑定到: {ZMQ_ADDRESS}")

# 2. 读取并编码图片
try:
    # 使用 OpenCV 读取图片 (无论是 PNG, JPG, BMP 格式都可以)
    image = cv2.imread(IMAGE_PATH)
    if image is None:
        raise FileNotFoundError(f"无法读取图片，请检查路径: {IMAGE_PATH}")

    # 将图像编码为 JPEG 格式。
    # worker_process.py 使用 cv2.imdecode，所以我们必须发送编码后的数据。
    # 95 是 JPEG 的质量参数 (0-100)
    is_success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not is_success:
        raise RuntimeError("使用 OpenCV 将图像编码为 JPEG 失败")

    # buffer 是一个 numpy 数组，我们将其转换为纯字节流以进行发送
    jpeg_bytes = buffer.tobytes()
    print(
        f"图片 '{IMAGE_PATH}' 已成功加载并编码为 {len(jpeg_bytes)} 字节的 JPEG 数据。"
    )

except Exception as e:
    print(f"错误: {e}")
    # 发生错误时，清理资源并退出
    socket.close()
    context.term()
    exit()


# 3. 等待订阅者连接
# 在 PUB/SUB 模式中，发布者启动后立即发送的消息可能会丢失，因为此时订阅者可能还没来得及连接上。
# 因此，在开始发送前稍作等待是一个好习惯。
print("等待订阅者连接... (等待1秒)")
time.sleep(1)


# 4. 循环发送图片数据
print("开始循环发送图片数据... 按 Ctrl+C 停止。")
try:
    while True:
        # 发送编码后的 JPEG 字节数据
        # PUB/SUB 模式不需要主题（topic），除非订阅者设置了过滤
        # 你的 worker 设置了 ""，表示接收所有消息
        socket.send(jpeg_bytes)
        print(f"已发送图片数据 ({len(jpeg_bytes)} bytes)")

        # 每隔2秒发送一次，方便观察
        time.sleep(2)

except KeyboardInterrupt:
    print("\n用户中断，正在停止发送程序...")

finally:
    # 5. 清理 ZMQ 资源
    print("正在关闭 ZMQ 套接字和上下文。")
    socket.close()
    context.term()
    print("程序已清理并退出。")
