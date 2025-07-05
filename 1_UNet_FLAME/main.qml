// main.qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia // 导入多媒体模块，用于视频播放

ApplicationWindow {
    id: root
    visible: true
    // 建议设置为你 RK3588 连接的显示器的分辨率
    width: 1920
    height: 1080
    title: qsTr("消防无人机中控系统")
    // 全屏显示，更具沉浸感
    // visibility: "FullScreen"

    // --- 1. 主背景 ---
    // 使用深邃的、有细微纹理的背景，增加专业感
    Rectangle {
        anchors.fill: parent
        color: "#0d1b2a" // 深夜蓝

        // 可选：添加一个网格背景，增加科技感
        Rectangle {
            anchors.fill: parent
            opacity: 0.05
            Image {
                anchors.fill: parent
                source: "images/tmp69C.png"
                fillMode: Image.Tile
            }
        }
    }

    // --- 2. 左上角: 视频播放窗口 ---
    Rectangle {
        id: videoContainerTopLeft
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 50 // 边距为屏幕宽度的 5%
        width: parent.width * 0.4 // 占据 40% 屏幕宽度
        height: parent.height * 0.4 // 占据 40% 屏幕高度
        color: "transparent" // 容器本身透明
        border.color: "#415a77" // 低调的边框
        border.width: 2

        Video {
            id: videoPlayerTopLeft
            anchors.fill: parent
            source: "file:///root/data/code/60_QT6/4_video_stream_out_of_sync/test.mp4"
            autoPlay: true
            loops: MediaPlayer.Infinite
            fillMode: VideoOutput.PreserveAspectCrop // 裁剪视频以填充，保持宽高比
        }
    }

    // --- 4. 左下角: 视频播放窗口 (来自 RKNN 的实时流) ---
    Rectangle {
        id: videoContainerBottomLeft
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 50
        width: parent.width * 0.4
        height: parent.height * 0.4
        color: "transparent"
        border.color: "#415a77" // 可以用一个更亮的颜色来区分，比如 "#ff6b6b"
        border.width: 2

        // ==================== 核心修改：用 Image 替换 Video ====================
        // Image 元素用于显示来自我们自定义 ImageProvider 的一帧帧图像。
        Image {
            id: liveVideoOutput
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop // 填充模式与Video元素类似

            // 'source' 的格式是 "image://<provider_id>/<image_id>"
            // 'livevideo' 是我们在 Python 中用 engine.addImageProvider("livevideo", ...) 注册的名字。
            // 'frame' 只是一个占位符ID，内容不重要。
            source: "image://livevideo/frame"

            // 禁用缓存很重要，确保每次 imageProvider 通知更新时，Image 元素都会去请求新的图像。
            cache: false
        }

        // Connections 元素用于监听来自 Python 的信号。
        Connections {
            // 'target' 指向我们在 Python 中通过 setContextProperty 暴露的对象。
            // 'imageProvider' 是我们在 main_ui.py 中设置的上下文属性名。
            target: imageProvider

            // 当 Python 端的 imageProvider 对象发出 'imageChanged' 信号时，这个函数会被调用。
            function onImageChanged() {
                // 这是一个强制刷新 Image 源的技巧。
                // QML 有时会缓存 source，即使内容变了也不更新。
                // 通过先设置为空再设回原值，可以强制它重新向 provider 请求图像。
                liveVideoOutput.source = ""
                liveVideoOutput.source = "image://livevideo/frame"
            }
        }
        // ========================================================================
    }

    // --- 3. 左上角: 信息面板 (覆盖在视频右侧或自定义位置) ---
    Rectangle {
        id: infoPanel
        width: 520
        height: 300
        anchors.left: videoContainerTopLeft.right // 紧贴在视频右侧
        anchors.bottom: videoContainerTopLeft.bottom
        anchors.leftMargin: 50
        color: "#1b263b99" // 半透明深蓝 (99 是十六进制的alpha值)
        border.color: "#00aeff" // 亮蓝色边框，突出显示
        border.width: 2
        radius: 5

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 3 // 紧凑布局

            Label { text: "飞机状态信息"; color: "#00aeff"; font.pixelSize: 18; font.bold: true; Layout.alignment: Qt.AlignHCenter }
            Item { Layout.fillWidth: true; Layout.preferredHeight: 10 } // 分隔线

            // 飞机 GPS 信息
            Label { text: "飞机GPS:"; color: "#e0e1dd"; font.pixelSize: 16 }
            Label { id: droneGpsLabel; text: "经度: 114.12345°, 纬度: 22.54321°"; color: "white"; font.pixelSize: 16 }

            Item { Layout.fillWidth: true; Layout.preferredHeight: 10 } // 间距

            // 飞机高度
            Label { text: "距地高度:"; color: "#e0e1dd"; font.pixelSize: 16 }
            Label { id: droneAltitudeLabel; text: "120.5 米"; color: "white"; font.pixelSize: 16 }

            Item { Layout.fillWidth: true; Layout.preferredHeight: 10 } // 间距

            // 火点 GPS 信息
            Label { text: "目标火点GPS:"; color: "#ff6b6b"; font.pixelSize: 16; font.bold: true } // 红色突出火点
            Label { id: fireGpsLabel; text: "经度: 114.12567°, 纬度: 22.54109°"; color: "white"; font.pixelSize: 16 }
        }
    }

    // --- 5. 右侧: 控制按钮面板 (网格布局) ---
    Rectangle {
        id: controlPanel
        // 调整尺寸以适应网格布局
        width: 520 // 增加了宽度以容纳两列按钮和间距
        height: 300 // 调整了高度

        // 将其锚定到右下角，更符合控制区域的习惯
        anchors.left: videoContainerBottomLeft.right
        anchors.top: videoContainerBottomLeft.top
        anchors.leftMargin: 50

        color: "#1b263b99"
        border.color: "#00aeff"
        border.width: 2
        radius: 10

        Component {
        id: controlButtonComponent
        Button {
            property string buttonText: "Default Text"
            property color defaultColor: "#415a77"
            property color hoverColor: "#778da9"
            property color pressedColor: "#0d1b2a"
            property color borderColor: "#e0e1dd"
            property bool enabled: true

            text: buttonText

            background: Rectangle {
                color: !parent.enabled ? "#333" : (parent.down ? parent.pressedColor : (parent.hovered ? parent.hoverColor : parent.defaultColor))
                radius: 5
                border.color: !parent.enabled ? "#555" : parent.borderColor
                border.width: 1
            }

            // ===== 这里是修改的部分 =====
            contentItem: Text {
                text: parent.text
                color: !parent.enabled ? "#888" : "white"
                font.pixelSize: 18
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                // 新增这一行来确保文本元素填充可用空间
                anchors.fill: parent
            }
            // =========================

            onClicked: {
                if (enabled) {
                    console.log(text + " 按钮被点击")
                }
            }
        }
    }

    GridLayout {
        anchors.fill: parent
        anchors.margins: 20
        columns: 2
        rowSpacing: 20
        columnSpacing: 20

        Repeater {
            model: [
                { "text": "自动巡飞", "isHighlight": false, "enabled": true },
                { "text": "锁定目标", "isHighlight": false, "enabled": true },
                { "text": "自动投弹", "isHighlight": true,  "enabled": true },
                { "text": "一键返航", "isHighlight": false, "enabled": true },
                { "text": "紧急悬停", "isHighlight": false, "enabled": true },
                { "text": "相机设置", "isHighlight": false, "enabled": false }
            ]

            delegate: Loader {
                Layout.preferredWidth: 220
                Layout.preferredHeight: 45
                sourceComponent: controlButtonComponent

                onLoaded: {
                    item.buttonText = modelData.text
                    item.enabled = modelData.enabled
                    if (modelData.isHighlight) {
                        item.defaultColor = "#c9184a"
                        item.hoverColor = "#ff4d6d"
                        item.pressedColor = "#800f2f"
                    }
                }
            }
        }
    }
}
}
