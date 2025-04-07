#include <Servo.h>
#include <ArduinoJson.h>
#include <MFRC522.h>
#include <SPI.h>

#define RST_PIN 9
#define SS_PIN 10
#define GREEN_LED 3
#define RED_LED 4

Servo servo;
MFRC522 rfid(SS_PIN, RST_PIN);

// System configuration
struct Config {
  int servoDefaultPos = 90;
  int servoAllowedPos = 180;
  String knownUIDs[5] = {"A1B2C3D4", "E5F6G7H8", "", "", ""}; // Add your known UIDs here
};

Config config;
int currentServoPos = 90;
bool servoControlEnabled = false;

void setup() {
  // Initialize hardware
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  servo.attach(5); // Servo on pin 5
  servo.write(config.servoDefaultPos);
  
  // Initialize serial communication
  Serial.begin(9600);
  while (!Serial); // Wait for serial port to connect
  
  // Initialize RFID reader
  SPI.begin();
  rfid.PCD_Init();
  
  Serial.println("System initialized. Ready for commands.");
}

void loop() {
  // Handle serial commands
  if (Serial.available() > 0) {
    handleSerialCommand();
  }

  // Check for RFID cards
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    handleRFID();
  }
  
  // Update servo position if control is enabled
  if (servoControlEnabled) {
    servo.write(currentServoPos);
  }
}

void handleSerialCommand() {
  String input = Serial.readStringUntil('\n');
  input.trim();
  
  // Check if it's a JSON configuration
  if (input.startsWith("{")) {
    DynamicJsonDocument doc(256);
    DeserializationError error = deserializeJson(doc, input);
    
    if (!error) {
      // Update servo positions from JSON
      if (doc.containsKey("default_pos")) {
        config.servoDefaultPos = doc["default_pos"];
      }
      if (doc.containsKey("allowed_pos")) {
        config.servoAllowedPos = doc["allowed_pos"];
      }
      
      Serial.println("Configuration updated successfully");
      return;
    }
  }
  
  // Handle simple commands
  if (input == "A") {
    enableServoControl();
  } else if (input == "D") {
    disableServoControl();
  } else if (input == "STATUS") {
    sendStatus();
  } else if (input.startsWith("SETPOS:")) {
    int newPos = input.substring(7).toInt();
    setServoPosition(newPos);
  }
}

void handleRFID() {
  // Extract UID
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  
  // Check if UID is known
  bool authorized = false;
  for (int i = 0; i < 5; i++) {
    if (uid == config.knownUIDs[i]) {
      authorized = true;
      break;
    }
  }
  
  // Visual feedback
  if (authorized) {
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(RED_LED, LOW);
    Serial.print("{\"status\":\"authorized\",\"uid\":\"");
    Serial.print(uid);
    Serial.println("\"}");
    
    // Enable servo control for authorized users
    enableServoControl();
  } else {
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
    Serial.print("{\"status\":\"unauthorized\",\"uid\":\"");
    Serial.print(uid);
    Serial.println("\"}");
    
    // Disable servo control for unauthorized users
    disableServoControl();
  }
  
  delay(1000); // LED feedback duration
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, LOW);
  
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void enableServoControl() {
  servoControlEnabled = true;
  currentServoPos = config.servoAllowedPos;
  Serial.println("{\"status\":\"servo_control_enabled\"}");
}

void disableServoControl() {
  servoControlEnabled = false;
  currentServoPos = config.servoDefaultPos;
  servo.write(currentServoPos);
  Serial.println("{\"status\":\"servo_control_disabled\"}");
}

void setServoPosition(int pos) {
  if (pos >= 0 && pos <= 180) {
    currentServoPos = pos;
    Serial.print("{\"status\":\"position_set\",\"angle\":");
    Serial.print(pos);
    Serial.println("}");
  } else {
    Serial.println("{\"error\":\"invalid_position\"}");
  }
}

void sendStatus() {
  Serial.print("{\"servo\":{\"current_pos\":");
  Serial.print(currentServoPos);
  Serial.print(",\"default_pos\":");
  Serial.print(config.servoDefaultPos);
  Serial.print(",\"allowed_pos\":");
  Serial.print(config.servoAllowedPos);
  Serial.print("},\"servo_control\":");
  Serial.print(servoControlEnabled ? "true" : "false");
  Serial.println("}");
}