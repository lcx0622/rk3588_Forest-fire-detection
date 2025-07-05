# worker_process.py (已修正)

import cv2
import time
import zmq
import numpy as np

# 导入 Process 和 Queue
from multiprocessing import Process, Queue


def worker_loop(frame_queue):
    """
    这个函数在独立的子进程中运行。
    :param frame_queue: 一个 multiprocessing.Queue，用于将图像发回主UI进程。
    """
    # --- ZMQ 客户端设置 ---
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    # 重要：连接到 sender 绑定的地址
    socket.connect("tcp://localhost:5454")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    print("[Worker Process] ZMQ client connected and listening.")

    # --- 主循环 ---
    while True:
        try:
            encoded_frame = socket.recv()
            np_arr = np.frombuffer(encoded_frame, np.uint8)
            bgr_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if bgr_frame is not None:
                # 为了防止队列无限增长，可以检查队列大小
                if frame_queue.qsize() < 50:  # 队列里最多只缓存10帧
                    frame_queue.put(bgr_frame)
                else:
                    # 如果队列满了，可以打印一个警告，或者 просто忽略这一帧
                    # print("[Worker Process] Queue is full, dropping frame.")
                    pass

        except zmq.ZMQError as e:
            # 当上下文终止时，recv 会抛出异常，这是正常的退出方式
            if e.errno == zmq.ETERM:
                print("[Worker Process] Context terminated, exiting loop.")
                break
            else:
                raise  # 重新抛出其他 ZMQ 异常
        except Exception as e:
            print(f"[Worker Process] Error: {e}")
            break

    print("[Worker Process] Stopping.")
    socket.close()
    context.term()


if __name__ == "__main__":
    print("[Main Process] Starting...")

    # 1. 创建一个跨进程共享的队列
    frame_queue = Queue(maxsize=10)

    # 2. 创建一个子进程，让它运行 worker_loop 函数，并把队列传给它
    #    target 是要运行的函数
    #    args 是一个元组，包含要传递给 target 函数的参数
    worker_process = Process(target=worker_loop, args=(frame_queue,))
    worker_process.daemon = True  # 设置为守护进程，这样主进程退出时它会自动结束
    worker_process.start()  # 启动子进程

    print("[Main Process] Worker process started. Waiting for frames...")

    # 3. 主进程现在可以自由地从队列中读取数据并显示
    while True:
        try:
            # 从队列中获取图像，如果队列为空，会阻塞等待
            # 设置一个超时，防止永久阻塞
            frame = frame_queue.get(timeout=1)

            cv2.imshow("Worker Frame", frame)

            # 按 'q' 键退出循环
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[Main Process] 'q' pressed, shutting down.")
                break

        except Exception as e:
            # 如果队列在超时时间内一直是空的，会抛出 Empty 异常
            # 我们可以利用这个机会检查子进程是否还在运行
            if not worker_process.is_alive():
                print("[Main Process] Worker process has died. Exiting.")
                break
            # 如果不是因为空队列，可以打印 "waiting..."
            # print("[Main Process] Waiting for frame...")

    # 4. 清理资源
    print("[Main Process] Cleaning up...")
    if worker_process.is_alive():
        worker_process.terminate()  # 强制终止子进程
    cv2.destroyAllWindows()
    print("[Main Process] Done.")
