const int photoPin = A0;
float photoValue = 0;
void setup() {
  Serial.begin(9600);

}

void loop() {
  photoValue = photoResistorRead(photoPin);
  Serial.println(photoValue);
}

int photoResistorRead(char analogPin){ 
  // Function to read 500 values from photoresistor and return average volatge value in milivolts.
  unsigned long sumVoltage = 0;
  float voltage = 0.0;
  
  for(int i =1; i<=250; i++){
    // Read values from analog pin connected to photoresistor
    sumVoltage+=analogRead(analogPin);
    delay(4);
  }

  voltage = (sumVoltage / 500);
  return voltage;
}
