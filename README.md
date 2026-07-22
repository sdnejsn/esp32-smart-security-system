## 📋 目录

- [系统架构](#-系统架构)
- [硬件清单](#-硬件清单)
- [快速开始](#-快速开始)
- [项目结构](#-项目结构)
- [核心算法](#-核心算法)
- [性能指标](#-性能指标)
- [best.pt引用来源](#-best.pt引用来源)

---

## 🏗️ 系统架构

```
┌─────────────────┐      Wi-Fi (STA)      ┌─────────────────────────────┐
│   ESP32-CAM     │ ◄──────────────────► │      本地PC服务器 (边缘)       │
│  (视觉采集节点)  │   HTTP MJPEG Stream  │  ┌─────────────────────┐    │
│  · GC2145摄像头  │                      │  │   Flask Web服务器    │    │
│  · 人脸抓拍上传  │ ◄───HTTP POST────────│  │   · /upload_face    │    │
│  · 火焰视觉检测  │   (0.5s/帧)          │  │   · /detect_fire    │    │
└─────────────────┘                      │  │   · /upload_sensor  │    │
                                         │  └─────────────────────┘    │
┌─────────────────┐      Wi-Fi (STA)     │  ┌─────────────────────┐    │
│   ESP32 Uno     │ ◄──────────────────► │  │  face_recognition   │    │
│  (环境感知节点)  │   HTTP POST JSON     │  │  YOLOv8 (best.pt)   │    │
│  · MQ-2烟雾传感  │   (5s/次)            │  │  SQLite database    │    │
│  · NTC温度传感   │                      │  └─────────────────────┘    │
│  · 蜂鸣器+LED   │                      └─────────────────────────────┘
└─────────────────┘                                      │
                                                         ▼
                                          ┌─────────────────────┐
                                          │   Web前端 (浏览器)   │
                                          │  · 实时传感器曲线    │
                                          │  · 人脸分类画廊      │
                                          │  · 火焰报警记录      │
                                          └─────────────────────┘
```

**设计哲学**：所有数据流转在家庭局域网内，**不上云、不收费、不泄露隐私**。

---

## 🔧 硬件清单

| 模块 | 型号 | 数量 | 关键参数 |
|-----|------|------|---------|
| 视觉节点 | ESP32-S3-EYE (N8R8) | 1 | 8MB Flash + 8MB PSRAM, GC2145摄像头 |
| 传感器节点 | ESP32 Uno (创乐博) | 1 | ESP32-WROOM-32, 240MHz |
| 烟雾传感器 | MQ-2 | 1 | SnO₂半导体, AO输出 |
| 温度传感器 | MH-系列 NTC热敏电阻 | 1 | 10kΩ NTC, AO输出 |
| 报警器 | 无源蜂鸣器 + 共阳极LED | 各1 | 1kHz PWM驱动 |

### ESP32-CAM关键配置

```cpp
// 摄像头参数（经稳定性调优）
config.pixel_format = PIXFORMAT_RGB565;   // GC2145不支持硬件JPEG
config.frame_size = FRAMESIZE_SVGA;       // 800x600，平衡画质与内存
config.xclk_freq_hz = 15000000;           // 15MHz，PSRAM带宽匹配
config.fb_count = 1;                      // 单缓冲，防长时间运行卡死
config.fb_location = CAMERA_FB_IN_PSRAM;  // 帧缓冲存外接PSRAM
```

> ⚠️ **重要**：GC2145传感器不支持 `PIXFORMAT_JPEG`，必须使用RGB565。Web服务器会自动软件编码为JPEG后通过MJPEG流传输。

---

## 🚀 快速开始

### 1. 硬件接线

**ESP32 Uno 传感器接线**

```
MQ-2 AO  ────► GPIO35 (ADC1_CH7)
NTC AO   ────► GPIO36 (ADC1_CH0)
蜂鸣器+  ────► GPIO17 (LEDC_CH0, 1kHz PWM)
LED阳极  ────► 3.3V
LED阴极  ────► GPIO14 (低电平点亮)
```

### 2. 烧录固件

**ESP32-CAM（Arduino IDE）**

- 开发板：ESP32S3 Dev Module
- Flash Size：8MB
- PSRAM：OPI PSRAM
- Partition Scheme：Huge APP (3MB No OTA/1MB SPIFFS)
- USB Mode：Hardware CDC and JTAG

**ESP32 Uno（Arduino IDE）**

- 开发板：ESP32 Dev Module
- 上传速度：921600

### 3. 配置网络

修改两处WiFi凭证：

```cpp
// CameraWebServer.ino & ESP32Uno.ino
const char* ssid = "YOUR_WIFI_SSID";      // 替换为你的WiFi
const char* password = "YOUR_WIFI_PASS";  // 替换为密码
```

> 建议全部设备在路由器绑定静态IP

### 4. 部署服务器

```bash
# 克隆仓库
git clone https://github.com/yourusername/smart-security-esp32.git
cd smart-security-esp32/pythonProject/SmartSecurity

# 安装依赖
pip install flask face-recognition opencv-python ultralytics numpy

# 准备已知人脸库
mkdir known_faces
cp /path/to/your/photos/*.jpg known_faces/

# 启动服务器
python server.py
```

### 5. 启动客户端

```bash
# 人脸检测与上传
python face_detection.py

# 浏览器访问监控面板
open http://<YOUR_SERVER_IP>:5000
```

---

## 📁 项目结构

```
project/
├── Arduino_project/
│   ├── CameraWebServer/          # ESP32-CAM固件
│   │   ├── CameraWebServer.ino   # 主程序（视频流+WiFi）
│   │   ├── camera_pins.h         # 引脚定义
│   │   └── app_httpd.cpp         # HTTP服务器（MJPEG流）
│   │
│   └── Sensors/                 # ESP32 Uno固件
│       └── Sensors.ino          # 传感器采集+报警+上传
│
├── pythonProject/
│   ├── face_detection.py         # 人脸检测客户端（OpenCV+Haar）
│   │
│   └── SmartSecurity/            # Flask主服务器
│       ├── server.py             # RESTful API + 识别引擎
│       ├── best.pt               # YOLOv8火焰检测模型
│       ├── database.db           # SQLite数据库（运行时生成）
│       ├── known_faces/          # 已知人脸库（需自行添加）
│       ├── templates/
│       │   └── index.html        # 前端监控面板
│       ├── uploads_known/        # 已知人员抓拍
│       ├── uploads_stranger/     # 陌生人抓拍
│       ├── uploads_unrecognized/ # 待确认抓拍
│       └── uploads_fires/        # 火焰检测抓拍
```

---

## 🧠 核心算法

### 人脸识别流程

```
MJPEG流 ──► OpenCV Haar检测人脸 ──► 0.5s定时上传 ──► face_recognition提取128维特征
                                                          │
                                                          ▼
                                                    欧氏距离比对
                                                          │
                              ┌──────────────────────────┼──────────────────────────┐
                         confidence≥0.6            0.5≤c<0.6                    c<0.5
                              │                         │                         │
                              ▼                         ▼                         ▼
                         已知人员                    待确认                      陌生人
                      uploads_known/           uploads_unrecognized/        uploads_stranger/
```

### 火焰检测流程

```
MJPEG流 ──► 0.5s定时截帧 ──► Haar预检人脸?
                                    │
                              检测到人脸 ──► 跳过YOLO（防人脸误报）
                                    │
                              未检测到人脸 ──► YOLOv8推理(best.pt)
                                                    │
                                             confidence≥0.8?
                                                    │
                                              是 ──► 保存火焰图片+数据库报警
                                              否 ──► 忽略
```

### 传感器融合策略

| 数据类型 | 上传频率 | 触发条件 | 本地动作 | 远程动作 |
|----------|----------|----------|----------|----------|
| 人脸图片 | 0.5s（有人脸时） | Haar检测到人脸 | - | HTTP POST + 识别分类 |
| 火焰检测 | 0.5s（每帧） | YOLO confidence≥0.8 | - | 保存图片 + DB记录 |
| 烟雾/温度 | 5s | ADC>1500 / ADC<1400 | 蜂鸣器+LED闪烁 | HTTP POST + 页面报警条 |

---

## 📊 性能指标

| 指标 | 数值 | 测试条件 |
|------|------|----------|
| 人脸识别准确率 | 75%已知 / 25%待确认 / 0%误报为已知 | 正脸，室内正常光照 |
| 陌生人识别率 | 100%（4位测试对象） | 网络清晰照片 |
| 火焰检测成功率 | 100%（50帧） | 手机屏幕播放火焰视频 |
| 抗干扰能力 | 0误报 | 阳光直射+台灯直射，各300帧 |
| 烟雾响应时间 | <1秒 | 打火机气体对准传感器 |
| 温度响应时间 | 瞬时 | 打火机火焰靠近NTC |
| 系统连续运行 | >24小时 | SVGA单缓冲配置 |
```

---

## 📚 best.pt引用来源

### YOLOv8 火焰检测模型

本项目使用的火焰检测模型 `best.pt` 基于以下开源项目训练：

- **项目名称**：Fire-Detection-using-YOLOv8
- **作者**：noorkhokhar99
- **来源**：GitHub
- **年份**：2023
- **链接**：[https://github.com/noorkhokhar99/Fire-Detection-using-YOLOv8](https://github.com/noorkhokhar99/Fire-Detection-using-YOLOv8)

特此感谢原作者的开源贡献。
