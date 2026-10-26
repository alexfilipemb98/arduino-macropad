#include <Keypad.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DHT.h"

// ================= PROTOCOL =================
// Lines of text ending in '\n', at 9600 baud.
// From the Arduino to the PC:
//   KEY:<0-9>       a key was pressed
//   TEMP:<degrees>  temperature in °C, e.g. TEMP:27.90
//   HUM:<percent>   relative humidity, e.g. HUM:55.00
//   SYSTEM:<text>   started, or an error
// From the PC to the Arduino:
//   TIME:<text>             date and time for the screen, every second (5 s without one and the PC counts as gone)
//   MSG:<text>              shows the text on the screen for 3 s
//   PIXEL:<id>,<r>,<g>,<b>  an LED's colour, id 0 to 2, each colour 0 to 255
// Each time the PC connects (its first TIME), the Arduino sends TEMP and HUM straight away.

// ================= SETTINGS =================

// --- OLED screen ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 32
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Characters that fit on a line at text size 2: 12 px each.
const byte LARGE_CHARACTERS = SCREEN_WIDTH / 12; // 10

// --- DHT22 sensor ---
#define DHTPIN 12
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

float lastTemperature = 0.0;
float lastHumidity = 0.0;
bool hasReading = false;  // There has been a good reading
bool sensorError = false; // The last reading failed

// --- NeoPixel LEDs ---
#define NUMPIXELS 3
#define PIN 2
Adafruit_NeoPixel pixels(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);

// --- Matrix keypad ---
const byte ROWS = 2;
const byte COLS = 5;
char keys[ROWS][COLS] = {
  {'5','6','7','8','9'},
  {'0','1','2','3','4'}
};
byte rowPins[ROWS] = {3, 4};
byte colPins[COLS] = {5, 6, 7, 8, 9};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// --- Timers ---
const unsigned long sensorInterval = 60000UL;      // Reads the DHT every 60 s
const unsigned long sensorRetryInterval = 5000UL;  // Tries again after 5 s while it fails
const unsigned long messageDuration = 3000UL;      // How long a message stays on the screen
const unsigned long pcMessageTimeout = 500UL;      // Waits for the PC's MSG before showing "Macro:"
const unsigned long pcTimeout = 5000UL;            // The PC counts as gone after 5 s without TIME
unsigned long lastSensorRead = 0;

// --- Line coming in from the PC ---
// Read a little at a time, without blocking, so the keys always answer.
const byte LINE_SIZE = 64;
char pcLine[LINE_SIZE];
byte pcLineLength = 0;

// --- Screen: time and messages ---
// In char[] rather than String: on an Arduino with 2 KB of RAM, String fragments the memory over time.
const char WAITING_FOR_PC[] = "Waiting for PC...";
char currentDateTime[24];
char messageText[32] = "";
bool showingMessage = false;
unsigned long messageShownAt = 0;
char lastKey = 0;
bool waitingForPcMessage = false;
unsigned long keyPressedAt = 0;

bool pcConnected = false;
unsigned long lastPcTime = 0;

// ================= SETUP =================
void setup() {
  Serial.begin(9600);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW); // On while the PC is connected

  strcpy(currentDateTime, WAITING_FOR_PC);

  pixels.begin();
  pixels.clear();
  pixels.show();

  dht.begin();

  if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("SYSTEM:OLED error"));
    for (;;);
  }
  display.setRotation(0); // Screen the right way up

  Serial.println(F("SYSTEM:Started"));

  // The DHT22 needs about 2 s after power-up: the first reading waits until then, and the
  // screen says "Reading..." rather than an error meanwhile.
  lastSensorRead = millis() - (sensorRetryInterval - 2000UL);
  updateScreen();
}

// ================= MAIN LOOP =================
void loop() {
  // 1. TAKE THE PC'S COMMANDS
  readSerial();

  // 2. CHECK THE KEYS
  char key = keypad.getKey();
  if (key) {
    onKeyPressed(key);
  }

  // millis() is read at each step: kept from the start of the loop, it would be behind a time set
  // since (a MSG just in) and the subtraction would wrap around.

  // 2.1. The PC didn't answer with a MSG: shows "Macro:"
  if (waitingForPcMessage && millis() - keyPressedAt >= pcMessageTimeout) {
    waitingForPcMessage = false;
    snprintf(messageText, sizeof(messageText), "Macro: %c", lastKey);
    showMessage();
  }

  // 3. TAKE THE MESSAGE OFF THE SCREEN AFTER 3 SECONDS
  if (showingMessage && millis() - messageShownAt >= messageDuration) {
    showingMessage = false;
    updateScreen();
  }

  // 4. READ THE DHT SENSOR (sooner while there's no good reading)
  unsigned long interval = (hasReading && !sensorError) ? sensorInterval : sensorRetryInterval;
  if (millis() - lastSensorRead >= interval) {
    lastSensorRead = millis();
    readSensor();
    if (pcConnected) sendSensor();
    if (!showingMessage) updateScreen();
  }

  // 5. The PC is gone: shows "Waiting for PC..."
  if (pcConnected && millis() - lastPcTime > pcTimeout) {
    pcConnected = false;
    digitalWrite(LED_BUILTIN, LOW);
    strcpy(currentDateTime, WAITING_FOR_PC);
    if (!showingMessage) updateScreen();
  }
}

// ================= FUNCTIONS =================

// Gathers the characters coming in into a line, and handles it once its '\n' arrives.
void readSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      pcLine[pcLineLength] = '\0';
      handleLine(pcLine);
      pcLineLength = 0;
    } else if (c != '\r' && pcLineLength < LINE_SIZE - 1) {
      // A line longer than the buffer is cut short, rather than written past it.
      pcLine[pcLineLength++] = c;
    }
  }
}

void handleLine(const char* line) {
  // A) The time
  if (strncmp(line, "TIME:", 5) == 0) {
    copyText(currentDateTime, sizeof(currentDateTime), line + 5);
    bool justConnected = !pcConnected;
    pcConnected = true;
    lastPcTime = millis();
    digitalWrite(LED_BUILTIN, HIGH);

    // The PC just connected: it gets the temperature and the humidity now, not at the next reading.
    if (justConnected) sendSensor();
    if (!showingMessage) updateScreen();
  }
  // B) A message for the screen
  else if (strncmp(line, "MSG:", 4) == 0) {
    copyText(messageText, sizeof(messageText), line + 4);
    waitingForPcMessage = false;
    showMessage();
  }
  // C) An LED's colour (e.g. PIXEL:0,255,0,0)
  else if (strncmp(line, "PIXEL:", 6) == 0) {
    int id, r, g, b;
    if (sscanf(line + 6, "%d,%d,%d,%d", &id, &r, &g, &b) == 4 && id >= 0 && id < NUMPIXELS) {
      pixels.setPixelColor(id, pixels.Color(constrain(r, 0, 255), constrain(g, 0, 255), constrain(b, 0, 255)));
      pixels.show();
    }
  }
}

void onKeyPressed(char key) {
  // Waits for the PC's MSG before showing "Macro:"
  lastKey = key;
  waitingForPcMessage = true;
  keyPressedAt = millis();

  // Only the key is sent: what it does is up to the PC.
  Serial.print(F("KEY:"));
  Serial.println(key);
}

void readSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    sensorError = true;
    return;
  }
  if (h > 100.0 || h < 0.0 || t < -40.0 || t > 80.0) return;

  sensorError = false;
  hasReading = true;
  lastTemperature = t;
  lastHumidity = h;
}

// Sends the last good reading to the PC; nothing while there's none.
void sendSensor() {
  if (!hasReading) return;

  Serial.print(F("TEMP:"));
  Serial.println(lastTemperature);
  Serial.print(F("HUM:"));
  Serial.println(lastHumidity);
}

void showMessage() {
  showingMessage = true;
  messageShownAt = millis();
  updateScreen();
}

// Copies text into a char[] without going past its size, always ending in '\0'.
void copyText(char* destination, size_t size, const char* source) {
  strncpy(destination, source, size - 1);
  destination[size - 1] = '\0';
}

void updateScreen() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // A message on the whole screen: large letters while it fits on a line, small ones when not.
  if (showingMessage) {
    bool fitsLarge = strlen(messageText) <= LARGE_CHARACTERS;
    display.setTextSize(fitsLarge ? 2 : 1);
    display.setCursor(0, fitsLarge ? 8 : 4);
    display.print(messageText);
  }
  // The usual view: the time at the top, the temperature and humidity below, with or without the PC.
  else {
    display.setTextSize(1);
    int width = strlen(currentDateTime) * 6;
    display.setCursor(width < SCREEN_WIDTH ? (SCREEN_WIDTH - width) / 2 : 0, 0);
    display.print(currentDateTime);

    display.drawLine(0, 11, SCREEN_WIDTH, 11, SSD1306_WHITE);

    display.setTextSize(2);
    display.setCursor(0, 15);
    if (!hasReading) {
      display.print(sensorError ? F("DHT error!") : F("Reading..."));
    } else {
      // The last good reading stays, even when a later one fails.
      display.print(lastTemperature, 1);
      display.print(F("C "));
      display.print(lastHumidity, 0);
      display.print(F("%"));
    }
  }
  display.display();
}
