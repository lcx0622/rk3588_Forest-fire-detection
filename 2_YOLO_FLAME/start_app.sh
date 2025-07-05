#!/bin/bash

# 脚本功能: 启动 RKNN 生产者和 Qt 消费者程序
# 使用方法: ./start_app.sh
# 关闭方法: 在运行此脚本的终端中按 Ctrl+C

echo "Starting the application..."

# 获取脚本所在的目录
BASE_DIR=$(dirname "$0")

# --- 定义你的Python环境和脚本路径 ---
# 如果你使用conda环境，请确保它已被激活，或者在这里指定Python解释器的完整路径
PYTHON_EXECUTABLE="/root/miniconda3/envs/ui/bin/python" # <-- 修改为你的Python解释器路径
PRODUCER_SCRIPT="$BASE_DIR/rknn_producer.py"
CONSUMER_SCRIPT="$BASE_DIR/qt_consumer.py"

# --- 定义生产者脚本的参数 ---
PRODUCER_ARGS="--video_path 2_video/test.mp4 --tpes 3"


# --- 清理函数，当脚本退出时会被调用 ---
cleanup() {
    echo -e "\nCaught Ctrl+C. Shutting down processes..."
    pkill -f "$PRODUCER_SCRIPT" # 使用pkill更可靠
    echo "Producer process(es) terminated."
    exit 0
}
trap cleanup SIGINT

# --- 在启动前，先清理一次可能残留的旧进程 ---
echo "Cleaning up any old producer processes..."
pkill -f "$PRODUCER_SCRIPT"
sleep 1 # 等待一秒确保进程已死掉

# 1. 在后台启动 RKNN 生产者
echo "Starting RKNN Producer in the background..."
$PYTHON_EXECUTABLE $PRODUCER_SCRIPT $PRODUCER_ARGS &
# 保存后台进程的PID，以便后续可以精确杀死它
PRODUCER_PID=$!
echo "Producer started with PID: $PRODUCER_PID"

# # 加一个短暂的延时，确保生产者已经初始化并绑定了端口
# sleep 2

# 2. 在前台启动 Qt 消费者
echo "Starting Qt Consumer in the foreground..."
$PYTHON_EXECUTABLE $CONSUMER_SCRIPT

# 当消费者程序（通常是Qt窗口）关闭后，脚本会继续执行到这里
echo "Consumer has exited. Cleaning up..."
# 确保生产者也被关闭
kill $PRODUCER_PID
echo "Shutdown complete."
