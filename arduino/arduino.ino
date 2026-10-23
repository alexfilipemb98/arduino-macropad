#include <Keypad.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DHT.h"

// ================= CONFIGURAÇÕES GERAIS =================

// --- Ecrã OLED ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 32
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- Sensor DHT22 ---
#define DHTPIN 12
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

float ultimaTemp = 0.0;
float ultimaHum = 0.0;
bool erroSensor = false;

// --- LEDs NeoPixel ---
#define NUMPIXELS 3
#define PIN 2
Adafruit_NeoPixel pixels(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);

// --- Teclado Matricial ---
const byte ROWS = 2;
const byte COLS = 5;
char keys[ROWS][COLS] = {
  {'0','1','2','3','4'},
  {'5','6','7','8','9'}
};
byte rowPins[ROWS] = {3, 4};
byte colPins[COLS] = {5, 6, 7, 8, 9};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// --- Temporizadores ---
unsigned long tempoAnteriorTemp = 0;
const long intervaloTemp = 60000; // Lê o DHT a cada 60 seg

// --- Controlo da Tecla no Ecrã ---
bool mostrarTeclaEcra = false;
String textoMacro = "";
unsigned long tempoMostrarTecla = 0;
char ultimaTecla = 0;
bool aguardarMsgPc = false;
unsigned long tempoAguardarMsg = 0;
const unsigned long timeoutMsgPc = 500; // Espera por MSG do PC antes do "Macro:"

// Variável para guardar a Hora enviada pelo Python
String dataHoraAtual = "A aguardar PC..."; 
bool pcConectado = false;
unsigned long ultimoHeartbeatPc = 0;
const unsigned long timeoutPcMs = 5000; // Considera PC desconectado apos 5s sem hora

// ================= SETUP =================
void setup() {
  Serial.begin(9600); 
  Serial.setTimeout(50); // Torna a leitura da Serial mais rápida
  pinMode(LED_BUILTIN, OUTPUT);

  pixels.begin();
  pixels.clear();
  pixels.show();

  dht.begin();

  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println("Erro no OLED");
    for(;;);
  }
  display.setRotation(0); // Orientação normal do ecrã
  
  Serial.println("SISTEMA:Iniciado");
  lerSensorDHT();
  atualizarEcra();
}

// ================= LOOP PRINCIPAL =================
void loop() {
  unsigned long tempoAtual = millis();

  // 1. RECEBER COMANDOS DO PYTHON
  if (Serial.available() > 0) {
    String mensagem = Serial.readStringUntil('\n');
    mensagem.trim(); 
    
    // A) Recebe a Hora
    if (mensagem.startsWith("HORA:")) {
      dataHoraAtual = mensagem.substring(5); 
      pcConectado = true;
      ultimoHeartbeatPc = millis();
      if (!mostrarTeclaEcra) atualizarEcra();
    }
    // B) Recebe Mensagem de Texto para o ecrã
    else if (mensagem.startsWith("MSG:")) {
      textoMacro = mensagem.substring(4);
      mostrarTeclaEcra = true;
      aguardarMsgPc = false;
      tempoMostrarTecla = millis();
      atualizarEcra();
    }
    // C) Recebe Comando para os NeoPixels (Ex: PIXEL:0,255,0,0)
    else if (mensagem.startsWith("PIXEL:")) {
      String dados = mensagem.substring(6);
      int v1 = dados.indexOf(',');
      int v2 = dados.indexOf(',', v1 + 1);
      int v3 = dados.indexOf(',', v2 + 1);

      if (v1 > 0 && v2 > 0 && v3 > 0) {
        int id = dados.substring(0, v1).toInt();
        int r = dados.substring(v1 + 1, v2).toInt();
        int g = dados.substring(v2 + 1, v3).toInt();
        int b = dados.substring(v3 + 1).toInt();
        
        pixels.setPixelColor(id, pixels.Color(r, g, b));
        pixels.show();
      }
    }
  }

  // 2. VERIFICAR BOTÕES
  char key = keypad.getKey();
  if (key) {
    lerTecla(key);
  }

  // 2.1. Se o PC nao respondeu com MSG, mostra "Macro:"
  if (aguardarMsgPc && (millis() - tempoAguardarMsg >= timeoutMsgPc)) {
    textoMacro = "Macro: ";
    textoMacro += ultimaTecla;
    mostrarTeclaEcra = true;
    aguardarMsgPc = false;
    tempoMostrarTecla = millis();
    atualizarEcra();
  }

  // 3. REMOVER A TECLA DO ECRÃ APÓS 3 SEGUNDOS (Corrigido!)
  if (mostrarTeclaEcra && (millis() - tempoMostrarTecla >= 3000)) {
    mostrarTeclaEcra = false;
    atualizarEcra();
  }

  // 4. LER SENSOR DHT
  if (tempoAtual - tempoAnteriorTemp >= intervaloTemp) {
    tempoAnteriorTemp = tempoAtual; 
    lerSensorDHT();
    if (!mostrarTeclaEcra) atualizarEcra(); 
  }

  // 5. Se perder ligacao ao PC, mostra "A aguardar PC..."
  if (pcConectado && (millis() - ultimoHeartbeatPc > timeoutPcMs)) {
    pcConectado = false;
    dataHoraAtual = "A aguardar PC...";
    if (!mostrarTeclaEcra) atualizarEcra();
  }
}

// ================= FUNÇÕES =================

void lerTecla(char key) {
  digitalWrite(LED_BUILTIN, HIGH);

  // Espera um MSG do PC antes de mostrar o "Macro:"
  ultimaTecla = key;
  aguardarMsgPc = true;
  tempoAguardarMsg = millis();

  // Envia a tecla apenas, a lógica dos LEDs ficou no Python!
  Serial.print("TECLA:");
  Serial.println(key);
  
  digitalWrite(LED_BUILTIN, LOW);
}

void lerSensorDHT() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    erroSensor = true;
    return;
  }
  if (h > 100.0 || h < 0.0 || t < -40.0 || t > 80.0) return; 

  erroSensor = false;
  ultimaTemp = t;
  ultimaHum = h;

  Serial.print("TEMP:");
  Serial.println(ultimaTemp);
}

void atualizarEcra() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // Modo Macro em ecrã inteiro
  if (mostrarTeclaEcra) {
    display.setTextSize(2);
    // Tentativa de centrar texto grande
    display.setCursor(0, 8);
    display.print(textoMacro);
  } 
  // Dashboard Normal
  else {
    display.setTextSize(1);
    int x_hora = 0;
    if(dataHoraAtual.length() > 5) { x_hora = (128 - (dataHoraAtual.length() * 6)) / 2; }
    display.setCursor(x_hora, 0); 
    display.print(dataHoraAtual);

    display.drawLine(0, 11, 128, 11, SSD1306_WHITE);

    display.setTextSize(2);
    if (erroSensor) {
      display.setCursor(0, 15);
      display.print("Erro DHT!");
    } else {
      display.setCursor(0, 15);
      display.print(ultimaTemp, 1);
      display.print("C ");
      display.print(ultimaHum, 0);
      display.print("%");
    }
  }
  display.display();
}