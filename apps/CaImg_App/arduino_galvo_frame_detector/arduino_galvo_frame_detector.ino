/*
   Created by ArduinoGetStarted.com

   This example code is in the public domain

   Tutorial page: https://arduinogetstarted.com/tutorials/arduino-serial-plotter
*/

const int MIR_RESET_THRE = -50;
const int BASELINE_THRE = 100;

int frame_ttl;
int frame_num;
int prev_grad;
int prev_val;
int cur_val;
int baseline_count;


void setup(){
  frame_ttl = 0;
  frame_num = 0;
  baseline_count = 0;
  
  cur_val = analogRead(A0);
  prev_val = cur_val;
  prev_grad = -1;
  digitalWrite(13,0);
  Serial.begin(115200);
}

void loop() {
  int cur_val = analogRead(A0);
  int cur_grad = cur_val - prev_val;

  if (cur_grad > MIR_RESET_THRE && prev_grad < MIR_RESET_THRE && prev_grad != -1) {
    frame_ttl = 500;
    frame_num ++;
  } else {
    frame_ttl = 0;
  }
  prev_grad = cur_grad;
  prev_val = cur_val;

  if (cur_val < 100) {
    baseline_count++;
  } else {
    baseline_count = 0;
  }

  if (baseline_count > 20) {
    frame_num = 0;
  }

//////////// DEBUGGING CODE //////////////
//  Serial.print("---");
//  Serial.print(millis());
//  Serial.print(",");
//  Serial.print(cur_val);
//  Serial.print(",");
//  Serial.print(frame_ttl);
//  Serial.println("+++");
/////////////////////////////////////////

//  if (frame_num > 0 && frame_ttl > 0) {
    Serial.print("---");
    Serial.print(millis());
    Serial.print(",");
    Serial.print(cur_val);
    Serial.print(",");
    Serial.print(frame_num);
    Serial.println("+++");
//  }
}
