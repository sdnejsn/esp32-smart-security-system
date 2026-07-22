#include <WiFi.h>
#include <HTTPClient.h>

// ==================== 用户配置区 ====================
const char* ssid = "HiwonderESP";
const char* password = "hiwonder";
const char* serverIP = "192.168.50.151";  // 修改为你的电脑IP
const int serverPort = 5000;
const String serverURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/upload_sensor";
const String deviceID = "esp32_uno_1";

// ==================== 引脚定义 ====================
const int SMOKE_AO_PIN = A7;    // 烟雾传感器模拟引脚
const int TEMP_AO_PIN = A0;     // 温度传感器模拟引脚
const int BUZZER_PIN = 17;      // 无源蜂鸣器 PWM 引脚
const int RED_LED_PIN = 14;     // 红色LED（共阳极，低电平点亮）

// ==================== 阈值 ====================
const int SMOKE_THRESHOLD = 1500;   // 烟雾阈值
const int TEMP_LOW = 1400;          // 温度下限（低于此值报警）

// ==================== 全局变量 ====================
int smokeAnalog = 0;
int tempAnalog = 0;
bool fireAlert = false;

unsigned long previousMillis = 0;
const long blinkInterval = 500;       // 闪烁间隔 500ms
bool ledState = false;                 // 记录红灯亮灭状态

unsigned long lastUploadTime = 0;
const long uploadInterval = 5000;      // 上传间隔 5秒

// ==================== 函数声明 ====================
void connectWiFi();
void readSensors();
void updateAlert();
void controlLEDandBuzzer();
void uploadSensorData(String sensorType, int value, int alertLevel);

// ==================== setup ====================
void setup() {
  Serial.begin(115200);

  pinMode(RED_LED_PIN, OUTPUT);
  digitalWrite(RED_LED_PIN, HIGH);  // 初始熄灭（共阳极高电平）

  ledcSetup(0, 2000, 8);            // 蜂鸣器 PWM 通道0
  ledcAttachPin(BUZZER_PIN, 0);
  ledcWriteTone(0, 0);              // 静音

  connectWiFi();
}

// ==================== loop ====================
void loop() {
  readSensors();
  updateAlert();
  controlLEDandBuzzer();

  unsigned long now = millis();
  if (now - lastUploadTime >= uploadInterval) {
    lastUploadTime = now;
    int smokeAlert = (smokeAnalog > SMOKE_THRESHOLD) ? 1 : 0;
    int tempAlert = (tempAnalog < TEMP_LOW) ? 1 : 0;   // 仅判断低于下限
    uploadSensorData("smoke", smokeAnalog, smokeAlert);
    uploadSensorData("temperature", tempAnalog, tempAlert);
  }

  delay(100);
}

// ==================== 连接 WiFi ====================
void connectWiFi() {
  Serial.print("连接到 WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi 连接成功");
  Serial.print("本地 IP: ");
  Serial.println(WiFi.localIP());
}

// ==================== 读取传感器 ====================
void readSensors() {
  smokeAnalog = analogRead(SMOKE_AO_PIN);
  tempAnalog = analogRead(TEMP_AO_PIN);
  Serial.printf("烟雾 AO:%4d | 温度 AO:%4d\n", smokeAnalog, tempAnalog);
}

// ==================== 更新火灾标志 ====================
void updateAlert() {
  // 火灾条件：烟雾超阈值 或 温度低于下限
  fireAlert = (smokeAnalog > SMOKE_THRESHOLD) || (tempAnalog < TEMP_LOW);
}

// ==================== 控制 LED 和蜂鸣器 ====================
void controlLEDandBuzzer() {
  unsigned long currentMillis = millis();

  if (fireAlert) {
    ledcWriteTone(0, 1000);   // 蜂鸣器响
    if (currentMillis - previousMillis >= blinkInterval) {
      previousMillis = currentMillis;
      ledState = !ledState;
      digitalWrite(RED_LED_PIN, ledState ? LOW : HIGH);
    }
  } else {
    ledcWriteTone(0, 0);      // 停止频率
    ledcWrite(0, 0);          // 强制占空比为 0，彻底关闭 PWM
    digitalWrite(RED_LED_PIN, HIGH);
  }
}

// ==================== 上传传感器数据 ====================
void uploadSensorData(String sensorType, int value, int alertLevel) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/json");

  String json = "{";
  json += "\"device_id\":\"" + deviceID + "\",";
  json += "\"sensor_type\":\"" + sensorType + "\",";
  json += "\"value\":" + String(value) + ",";
  json += "\"alert_level\":" + String(alertLevel);
  json += "}";

  int httpCode = http.POST(json);
  if (httpCode > 0) {
    Serial.printf("✅ 上传 %s 成功，HTTP %d\n", sensorType.c_str(), httpCode);
  } else {
    Serial.printf("❌ 上传 %s 失败，错误: %s\n", sensorType.c_str(), http.errorToString(httpCode).c_str());
  }
  http.end();
}