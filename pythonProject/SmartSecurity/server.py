import os
import sqlite3
import datetime
import traceback
from flask import Flask, request, jsonify, render_template
import face_recognition
import numpy as np
from ultralytics import YOLO
import cv2
from flask import send_from_directory

app = Flask(__name__)

# ==================== 配置目录 ====================
KNOWN_FACES_DIR = 'known_faces'  # 已知人脸库（用于比对）
UPLOAD_TEMP_FOLDER = 'uploads_temporary'  # 临时文件夹，先存放所有上传的人脸图片
UPLOAD_KNOWN_FOLDER = 'uploads_known'  # 识别为已知人员且置信度 >=0.6
UPLOAD_UNRECOGNIZED_FOLDER = 'uploads_unrecognized'  # 置信度在 0.5~0.6 之间
UPLOAD_STRANGER_FOLDER = 'uploads_stranger'  # 陌生人或置信度 <0.5
UPLOAD_FIRES_FOLDER = 'uploads_fires'  # 火焰图片

# 创建目录
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
os.makedirs(UPLOAD_TEMP_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_KNOWN_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_UNRECOGNIZED_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_STRANGER_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FIRES_FOLDER, exist_ok=True)

# ==================== 加载火焰检测模型 ====================
# 请将 fireModel.pt 放在项目根目录
fire_model = YOLO("best.pt")
# 加载人脸检测分类器（用于火焰检测前跳过人脸）
face_cascade_for_fire = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


# ==================== 数据库初始化 ====================
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS access_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  person_name TEXT,
                  image_path TEXT,
                  is_stranger INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  device_id TEXT,
                  sensor_type TEXT,
                  value REAL,
                  alert_level INTEGER)''')
    conn.commit()
    conn.close()


init_db()


# ==================== 加载已知人脸 ====================
def load_known_faces():
    known_encodings = []
    known_names = []
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            path = os.path.join(KNOWN_FACES_DIR, filename)
            image = face_recognition.load_image_file(path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                known_encodings.append(encodings[0])
                name = os.path.splitext(filename)[0]
                known_names.append(name)
                print(f"加载已知人脸: {name}")
    return known_encodings, known_names


known_face_encodings, known_face_names = load_known_faces()


# ==================== API: 接收图片并识别（人脸） ====================
@app.route('/upload_face', methods=['POST'])
def upload_face():
    if 'image' not in request.files:
        return jsonify({'error': 'No image part'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # 先保存到临时文件夹
    temp_filename = f"face_{timestamp}_temp.jpg"
    temp_path = os.path.join(UPLOAD_TEMP_FOLDER, temp_filename)
    file.save(temp_path)

    # 加载图片进行人脸识别
    unknown_image = face_recognition.load_image_file(temp_path)
    unknown_encodings = face_recognition.face_encodings(unknown_image)

    result = {
        'timestamp': timestamp,
        'persons': [],
        'is_stranger': False
    }

    final_person_name = "陌生人"
    final_confidence = 0.0
    is_known = False

    if len(unknown_encodings) == 0:
        os.remove(temp_path)
        return jsonify({'error': 'No face detected in image'}), 400

    unknown_encoding = unknown_encodings[0]
    if known_face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, unknown_encoding, tolerance=0.5)
        face_distances = face_recognition.face_distance(known_face_encodings, unknown_encoding)
        best_match_index = np.argmin(face_distances) if face_distances.size > 0 else -1
        if best_match_index != -1 and matches[best_match_index]:
            matched_name = known_face_names[best_match_index]
            confidence = 1 - face_distances[best_match_index]
            result['persons'].append({'name': matched_name, 'confidence': float(confidence)})
            final_person_name = matched_name
            final_confidence = confidence
            is_known = True
            result['is_stranger'] = False
            print(f"[DEBUG] 识别为已知人员: {matched_name}, 置信度: {confidence:.2f}")
        else:
            result['persons'].append({'name': '陌生人', 'confidence': 0.0})
            result['is_stranger'] = True
            final_person_name = "陌生人"
            final_confidence = 0.0
            print("[DEBUG] 识别为陌生人")
    else:
        result['persons'].append({'name': '陌生人', 'confidence': 0.0})
        result['is_stranger'] = True
        final_person_name = "陌生人"
        final_confidence = 0.0
        print("[DEBUG] 已知人脸库为空，判定为陌生人")

    # 根据识别结果移动文件
    if is_known:
        if final_confidence >= 0.6:
            target_folder = UPLOAD_KNOWN_FOLDER
            print(f"[分类] 置信度 {final_confidence:.2f} >= 0.6，归为已知人员")
        elif final_confidence >= 0.5:
            target_folder = UPLOAD_UNRECOGNIZED_FOLDER
            print(f"[分类] 置信度 {final_confidence:.2f} 在 [0.5,0.6) 区间，归为待确认")
        else:
            target_folder = UPLOAD_STRANGER_FOLDER
            final_person_name = "陌生人"
            result['is_stranger'] = True
            print(f"[分类] 置信度 {final_confidence:.2f} < 0.5，归为陌生人")
    else:
        target_folder = UPLOAD_STRANGER_FOLDER
        final_person_name = "陌生人"
        result['is_stranger'] = True
        print("[分类] 陌生人")

    conf_str = f"conf{final_confidence:.2f}".replace('.', '_')
    final_filename = f"face_{timestamp}_{conf_str}.jpg"
    final_path = os.path.join(target_folder, final_filename)
    os.rename(temp_path, final_path)
    result['image_path'] = final_path

    # 保存记录到数据库
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    is_stranger_db = 1 if final_person_name == "陌生人" else 0
    c.execute('''INSERT INTO access_logs (timestamp, person_name, image_path, is_stranger)
                 VALUES (?, ?, ?, ?)''',
              (datetime.datetime.now(), final_person_name, final_path, is_stranger_db))
    conn.commit()
    conn.close()

    return jsonify(result)


# ==================== API: 火焰检测 ====================
@app.route('/detect_fire', methods=['POST'])
def detect_fire():
    if 'image' not in request.files:
        return jsonify({'error': 'No image part'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # 读取图片
    img_bytes = file.read()
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    # 先进行人脸检测，如果存在人脸则直接跳过火焰检测
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade_for_fire.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
    if len(faces) > 0:
        # 有人脸，不进行火焰检测，直接返回无火焰
        return jsonify({'flames': [], 'count': 0, 'reason': 'face_detected'})

    # YOLO 推理
    results = fire_model(img)
    flames = []
    for r in results:
        boxes = r.boxes
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                name = fire_model.names[cls]
                # 只接受置信度 > 0.8 的火焰/火苗检测
                if name.lower() in ['fire', 'flame'] and conf > 0.8:
                    flames.append({
                        'class': name,
                        'confidence': conf,
                        'bbox': box.xyxy[0].tolist()
                    })

    # 如果检测到火焰，保存图片并记录报警
    if flames:
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"fire_{timestamp}.jpg"
        filepath = os.path.join(UPLOAD_FIRES_FOLDER, filename)
        cv2.imwrite(filepath, img)

        # 记录到 fire_alerts 表
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS fire_alerts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp DATETIME,
                      image_path TEXT)''')
        c.execute('''INSERT INTO fire_alerts (timestamp, image_path) VALUES (?, ?)''',
                  (datetime.datetime.now(), filepath))
        conn.commit()
        conn.close()

        # 同时写入 sensor_data 表作为报警记录
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('''INSERT INTO sensor_data (timestamp, device_id, sensor_type, value, alert_level)
                     VALUES (?, ?, ?, ?, ?)''',
                  (datetime.datetime.now(), 'esp32_cam', 'fire', 1, 2))
        conn.commit()
        conn.close()

        print(f"🔥 检测到火焰！已保存图片: {filepath}")

    return jsonify({'flames': flames, 'count': len(flames)})


# ==================== API: 接收传感器数据 ====================
@app.route('/upload_sensor', methods=['POST'])
def upload_sensor():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data'}), 400

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO sensor_data (timestamp, device_id, sensor_type, value, alert_level)
                 VALUES (?, ?, ?, ?, ?)''',
              (datetime.datetime.now(),
               data.get('device_id', 'esp32_uno'),
               data.get('sensor_type'),
               data.get('value'),
               data.get('alert_level', 0)))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


# ==================== API: 获取历史数据 ====================
@app.route('/get_history')
def get_history():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT timestamp, person_name, is_stranger FROM access_logs ORDER BY timestamp DESC LIMIT 20''')
    access_logs = c.fetchall()
    c.execute('''SELECT timestamp, sensor_type, value, alert_level FROM sensor_data ORDER BY timestamp DESC LIMIT 50''')
    sensor_data = c.fetchall()
    conn.close()
    return jsonify({
        'access_logs': access_logs,
        'sensor_data': sensor_data
    })


# ==================== API: 火焰报警（兼容旧接口） ====================
@app.route('/fire_alarm', methods=['POST'])
def fire_alarm():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON'}), 400
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO sensor_data (timestamp, device_id, sensor_type, value, alert_level)
                 VALUES (?, ?, ?, ?, ?)''',
              (datetime.datetime.now(),
               data.get('device_id', 'esp32_cam'),
               'fire',
               1,
               2))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


# ==================== API: 上传火焰图片（兼容旧接口） ====================
@app.route('/upload_fire', methods=['POST'])
def upload_fire():
    if 'image' not in request.files:
        return jsonify({'error': 'No image part'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"fire_{timestamp}.jpg"
    filepath = os.path.join(UPLOAD_FIRES_FOLDER, filename)
    file.save(filepath)

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fire_alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  image_path TEXT)''')
    c.execute('''INSERT INTO fire_alerts (timestamp, image_path) VALUES (?, ?)''',
              (datetime.datetime.now(), filepath))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'image_path': filepath})


# ==================== 主页 ====================
@app.route('/')
def index():
    return render_template('index.html')


# ==================== API: 获取指定文件夹的图片列表 ====================
@app.route('/get_images/<folder>', methods=['GET'])
def get_images(folder):
    # 允许的文件夹名称映射到实际路径
    allowed_folders = {
        'known': UPLOAD_KNOWN_FOLDER,
        'stranger': UPLOAD_STRANGER_FOLDER,
        'unrecognized': UPLOAD_UNRECOGNIZED_FOLDER,
        'fires': UPLOAD_FIRES_FOLDER
    }
    if folder not in allowed_folders:
        return jsonify({'error': 'Invalid folder'}), 400

    folder_path = allowed_folders[folder]
    images = []
    # 支持常见图片格式
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            # 获取文件修改时间作为排序依据
            filepath = os.path.join(folder_path, filename)
            mtime = os.path.getmtime(filepath)
            images.append({
                'name': filename,
                'path': f'/{folder_path}/{filename}',  # 前端可直接访问的相对路径
                'timestamp': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    # 按时间倒序排列（最新的在前）
    images.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(images)


# 为了让前端能直接访问图片文件，需要添加静态文件路由（Flask 默认无法访问 uploads_* 目录）
# 添加以下路由（放在所有路由最后）：
@app.route('/uploads_known/<path:filename>')
def uploads_known(filename):
    return send_from_directory(UPLOAD_KNOWN_FOLDER, filename)


@app.route('/uploads_stranger/<path:filename>')
def uploads_stranger(filename):
    return send_from_directory(UPLOAD_STRANGER_FOLDER, filename)


@app.route('/uploads_unrecognized/<path:filename>')
def uploads_unrecognized(filename):
    return send_from_directory(UPLOAD_UNRECOGNIZED_FOLDER, filename)


@app.route('/uploads_fires/<path:filename>')
def uploads_fires(filename):
    return send_from_directory(UPLOAD_FIRES_FOLDER, filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
