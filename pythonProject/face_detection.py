import requests
import cv2
import numpy as np
import time

# ==================== 静态配置 ====================
SERVER_URL = "http://<YOUR_SERVER_IP>:5000/upload_face"
FIRE_DETECT_URL = "http://<YOUR_SERVER_IP>:5000/detect_fire"
STREAM_URL = "http://<ESP32_CAM_IP>:81/stream"

# 火焰检测间隔（秒）
FIRE_INTERVAL = 0.5
last_fire_time = 0

# 人脸上传间隔（秒）
FACE_INTERVAL = 0.5
last_face_time = 0

# 初始化人脸分类器
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

print("尝试连接 ESP32-CAM MJPEG 流...")
headers = {"User-Agent": "Mozilla/5.0"}

def upload_image(url, frame, tag="图片"):
    """通用上传函数（人脸识别用）"""
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return None
    files = {'image': (f'{tag}.jpg', buffer.tobytes(), 'image/jpeg')}
    try:
        r = requests.post(url, files=files, timeout=2)
        if r.status_code == 200:
            print(f"✅ {tag}上传成功")
            return r.json()
        else:
            print(f"❌ {tag}上传失败，HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ {tag}上传异常: {e}")
    return None

def upload_fire_detection(frame):
    """将当前帧发送到火焰检测接口"""
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return
    files = {'image': ('frame.jpg', buffer.tobytes(), 'image/jpeg')}
    try:
        r = requests.post(FIRE_DETECT_URL, files=files, timeout=2)
        if r.status_code == 200:
            result = r.json()
            if result.get('count', 0) > 0:
                print(f"🔥 服务器检测到火焰！结果: {result['flames']}")
        else:
            print(f"火焰检测请求失败: {r.status_code}")
    except Exception as e:
        print(f"火焰检测异常: {e}")

# ==================== 主循环 ====================
while True:
    try:
        r = requests.get(STREAM_URL, stream=True, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"连接失败，状态码: {r.status_code}，3秒后重试...")
            time.sleep(3)
            continue

        print("🚀 监控已就绪，开始人脸检测...")
        bytes_data = bytes()

        for chunk in r.iter_content(chunk_size=1024):
            bytes_data += chunk
            a = bytes_data.find(b'\xff\xd8')
            b = bytes_data.find(b'\xff\xd9')

            if a != -1 and b != -1:
                jpg = bytes_data[a:b+2]
                bytes_data = bytes_data[b+2:]
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                if frame is None:
                    continue

                current_time = time.time()

                # ---------- 人脸检测与定时上传 ----------
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))

                if len(faces) > 0:
                    # 控制人脸上传间隔
                    if current_time - last_face_time >= FACE_INTERVAL:
                        last_face_time = current_time
                        res = upload_image(SERVER_URL, frame, "人脸")
                        if res and res.get('is_stranger'):
                            cv2.putText(frame, "STRANGER!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    # 绘制人脸框（无论是否上传都绘制）
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

                # ---------- 火焰检测（定时） ----------
                if current_time - last_fire_time >= FIRE_INTERVAL:
                    last_fire_time = current_time
                    upload_fire_detection(frame)

                # 显示画面
                cv2.imshow('ESP32-CAM 人脸识别', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    exit()

    except Exception as e:
        print(f"连接断开: {e}，正在重连...")
        time.sleep(3)