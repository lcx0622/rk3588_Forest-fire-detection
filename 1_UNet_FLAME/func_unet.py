# func_unet.py
import cv2
import numpy as np

IMG_SIZE = (256, 256)  # UNet模型期望的输入尺寸

# 可视化方式选择 (通过取消注释选择一种)
VISUALIZATION_MODE = "OVERLAY"  # 可选: "SIDE_BY_SIDE", "OVERLAY", "MASK_ONLY"
import numpy as np


def sigmoid_numpy(x):
    """
    计算输入 x (可以是标量或 NumPy 数组) 的 Sigmoid 值。
    """
    return 1 / (1 + np.exp(-x))


# 这个函数负责接收一个原始视频帧 (frame)，并将其转换NHWC
def preprocess_frame_for_unet(frame, target_size):
    """
    为UNet模型预处理视频帧。
    返回: NHWC格式的图像数据 (通常是uint8或float32，取决于模型)
    """
    img_resized = cv2.resize(frame, target_size)  # shape: (height, width, 3)

    # 颜色通道: 检查您的模型是否期望RGB。OpenCV读取的是BGR。
    # 如果模型期望RGB:
    img_resized = cv2.cvtColor(
        img_resized, cv2.COLOR_BGR2RGB
    )  # shape: (height, width, 3)

    # 数据类型和归一化:
    # RKNN模型通常在转换时配置了均值和标准差，可直接输入uint8。
    # 假设模型期望 uint8 HWC (BGR 或 RGB 取决于上面)
    img_processed_hwc = img_resized.astype(np.uint8)  # shape: (height, width, 3)

    # 增加batch维度，变为 NHWC，模型输入为 (1, height, width, 3)
    img_nhwc = np.expand_dims(img_processed_hwc, axis=0)  # shape: (1, height, width, 3)
    # # 确保是NHWC格式
    # img_nchw = img_nhwc.transpose(0, 3, 1, 2) # shape: (1, 3, height, width)
    return img_nhwc


def postprocess_unet_output(raw_output_tensor, original_frame_shape):

    # 假设输出是 (1, 1, H, W) (NCHW, 单通道概率图或logits)
    # 或 (1, H, W, 1) (NHWC)
    segmentation_map = None
    if len(raw_output_tensor.shape) == 4:
        if raw_output_tensor.shape[1] == 1:  # NCHW (1,1,H,W)
            segmentation_map = raw_output_tensor[0, 0, :, :]
        elif raw_output_tensor.shape[3] == 1:  # NHWC (1,H,W,1)
            segmentation_map = raw_output_tensor[0, :, :, 0]
    elif (
        len(raw_output_tensor.shape) == 3 and raw_output_tensor.shape[0] == 1
    ):  # (1,H,W)
        segmentation_map = raw_output_tensor[0, :, :]
    elif len(raw_output_tensor.shape) == 2:  # (H,W)
        segmentation_map = raw_output_tensor

    if segmentation_map is None:
        print(f"无法处理的输出形状: {raw_output_tensor.shape}。尝试squeeze。")
        try:
            segmentation_map = np.squeeze(raw_output_tensor)
            if len(segmentation_map.shape) != 2:
                print(f"Squeezed shape {segmentation_map.shape} is not 2D.")
                return None  # 返回None表示处理失败
        except Exception as e:
            print(f"Squeeze失败: {e}")
            return None

    # 增加一个sigmoid
    segmentation_map = sigmoid_numpy(segmentation_map)
    # 将概率图转换为 0-255 的 uint8 图像
    output_mask_uint8_model_size = (segmentation_map * 255).astype(np.uint8)

    # 将清理后的掩码调整回原始视频帧的尺寸
    output_mask_resized = cv2.resize(
        output_mask_uint8_model_size,  # <--- 修改：使用我们最终稳定化的掩码
        (original_frame_shape[1], original_frame_shape[0]),
        interpolation=cv2.INTER_NEAREST,
    )

    return output_mask_resized


# <--- 1. 修改 myFunc 的函数签名，增加 lock 参数
def myFunc(rknn_lite_instance, original_frame):
    """
    在rknnPoolExecutor中运行的回调函数。
    rknn_lite_instance: 由线程池提供的一个RKNNLite对象。
    original_frame: 从视频捕获的原始帧。
    lock: 用于同步推理调用的线程锁。
    返回: 处理后的帧 (NumPy array) 或 None。
    Original frame shape: (480, 640, 3)
    """
    if original_frame is None:
        return None

    # 防御性拷贝，确保后续操作在本线程的私有数据上进行
    original_frame_copy = original_frame.copy()

    # 1. 预处理帧 (这部分可以在锁外并行执行)
    input_data_nhwc = preprocess_frame_for_unet(original_frame_copy, IMG_SIZE)
    # 2. 模型推理 (这是关键的临界区)
    # <--- 2. 使用 with 语句来自动获取和释放锁
    # 在这个 'with' 代码块内，一次只有一个线程可以执行
    # 这可以防止多个线程同时调用 inference() 导致硬件冲突
    outputs = rknn_lite_instance.inference(inputs=[input_data_nhwc])

    # 锁在 'with' 块结束时自动释放，其他等待的线程可以进入

    if not outputs:
        print("---------------------------------模型推理没有输出。")
        return None

    # 3. 后处理模型输出 (这部分也可以在锁外并行执行)
    processed_mask = postprocess_unet_output(
        outputs[0], original_frame_copy.shape
    )  # Processed mask shape: (480, 640)
    # #打印processed_mask的最大值和最小值
    # print(f"Processed mask min: {np.min(processed_mask)}, max: {np.max(processed_mask)}")
    # #打印processed_mask的形状
    # print(f"Processed mask shape: {processed_mask.shape}")
    if processed_mask is None:
        print("---------------------------------后处理掩码失败。")
        return None

    h, w, _ = original_frame.shape
    output_display_frame = None

    # --------------------------------------------------------
    if VISUALIZATION_MODE == "SIDE_BY_SIDE":
        # 方式 A: 左右拼接
        mask_bgr_display = cv2.cvtColor(processed_mask, cv2.COLOR_GRAY2BGR)
        # 确保尺寸一致 (postprocess_unet_output 已经处理了)
        if mask_bgr_display.shape[0] != h or mask_bgr_display.shape[1] != w:
            mask_bgr_display = cv2.resize(mask_bgr_display, (w, h))
        output_display_frame = np.hstack((original_frame, mask_bgr_display))
    # --------------------------------------------------------
    elif VISUALIZATION_MODE == "OVERLAY":
        # 方式 B: 将掩码叠加到原始帧上
        # original_frame_bgr = cv2.cvtColor(original_frame, cv2.COLOR_GRAY2BGR)
        # 创建一个简单的叠加效果：比如将分割出的区域在原图上用半透明红色标出
        # 注意：这种叠加方式对于灰度掩码可能效果不直观，
        # 你可能需要先对 processed_mask 进行阈值化得到二值掩码
        # color_overlay = original_frame.copy() # 不需要，addWeighted会创建新图
        color_mask_viz = np.zeros_like(original_frame)
        # 假设分割目标是较亮区域
        color_mask_viz[processed_mask > 128] = [0, 255, 0]  # BGR红色 (目标区域)
        # 你也可以让非目标区域是原始图像，目标区域是彩色掩码
        # color_mask_viz[processed_mask <= 128] = [0, 255, 0] # BGR绿色 (背景区域)
        alpha = 0.4  # 掩码的透明度
        beta = 1 - alpha  # 原始帧的透明度
        output_display_frame = cv2.addWeighted(
            original_frame, beta, color_mask_viz, alpha, 0
        )
    # --------------------------------------------------------
    elif VISUALIZATION_MODE == "MASK_ONLY":
        # 方式 C: 只输出掩码 (转为BGR以便VideoWriter处理)
        output_display_frame = cv2.cvtColor(processed_mask, cv2.COLOR_GRAY2BGR)
        # 确保尺寸与原始帧一致，如果VideoWriter期望固定尺寸
        if output_display_frame.shape[0] != h or output_display_frame.shape[1] != w:
            output_display_frame = cv2.resize(output_display_frame, (w, h))
    # --------------------------------------------------------
    return output_display_frame  # 返回组合后的帧
