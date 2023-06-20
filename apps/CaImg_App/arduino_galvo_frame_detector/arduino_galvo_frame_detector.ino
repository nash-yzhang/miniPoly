#include <Wire.h>
#include <Adafruit_MotorShield.h>
#include <utility/Adafruit_MS_PWMServoDriver.h>
#include <Servo.h>

Adafruit_MotorShield AFMS = Adafruit_MotorShield(); // Create an instance of the Adafruit Motor Shield library
Adafruit_StepperMotor *stepper1 = AFMS.getStepper(200, 2); // 200 steps per revolution, motor port number 2
Servo flagServoMotor;
Servo radiusServoMotor;


const int ledPin = 8;
int flag;
int lightOn;

void setup() {
  Serial.begin(9600);
  AFMS.begin(); // Initialize the Adafruit Motor Shield
  stepper1->setSpeed(100); // Set the motor speed (RPM)
  flagServoMotor.attach(9); // Attach servo to pin 9
  radiusServoMotor.attach(10); // Attach servo to pin 10
  flag = 0;
  lightOn = 0;
  pinMode(ledPin, OUTPUT); // Set LED pin as output
}

void loop() {
  if (Serial.available()) {
    String receivedString = Serial.readStringUntil('\n');
    if (receivedString.length() > 0) {
      if (receivedString.startsWith("s1")) {
        int angle = receivedString.substring(2).toInt();
        executeRadiusServoCommand(angle);
      } else if (receivedString.startsWith("s2")) {
        int angle = receivedString.substring(2).toInt();
        executeFlagServoCommand(angle);
      } else if (receivedString.startsWith("pin")) {
        executePinCommand(receivedString);
      } else {
        executeStepperCommand(receivedString);
      }
    }
  }
}

void executeStepperCommand(String commandString) {
  char command = commandString.charAt(0);
  char motorIdx = commandString.charAt(1);
  int steps = commandString.substring(2).toInt();
  if (motorIdx == '1'){
    if (command == 'f') {
    stepper1->step(steps, FORWARD, DOUBLE); // Rotate motor forward by the specified number of steps
    } else if (command == 'b') {
      stepper1->step(steps, BACKWARD, DOUBLE); // Rotate motor backward by the specified number of steps
    }
  }
}

void executeRadiusServoCommand(int angle) {
  radiusServoMotor.write(angle); // Set the servo motor to the specified angle
}

void executeFlagServoCommand(int angle) {
  flagServoMotor.write(angle); // Set the servo motor to the specified angle
}

void executePinCommand(String commandString) {
  int pin_num = commandString.substring(3,5).toInt();
  float pin_val = commandString.substring(5).toFloat();
  Serial.println(pin_num);
  Serial.println(pin_val);
  digitalWrite(pin_num, pin_val);
}

void toggleFlagServoCommand() {
  if (flag == 0){
      flagServoMotor.write(90); // Set the servo motor to the specified angle
      flag = 1;
  } else {
      flagServoMotor.write(0); // Set the servo motor to the specified angle
      flag = 0;
  }
}

void toggleLightCommand() {
  if (lightOn == 0){
      digitalWrite(ledPin, 1); // Set the servo motor to the specified angle
      lightOn = 1;
  } else {
      digitalWrite(ledPin, 0); // Set the servo motor to the specified angle
      lightOn = 0;
  }
}
