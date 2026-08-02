#include <Wire.h>

// ピン定義 (Pico)
#define I2C_SDA 4
#define I2C_SCL 5

// --- I2C アドレス定義 ---
#define PIANO_1_ADDR 0x28 // Piano HAT 前半 (Pad 0〜7)
#define PIANO_2_ADDR 0x2B // Piano HAT 後半 (Pad 8〜15)
#define DRUM_ADDR    0x2C // Drum HAT (Pad 0〜7)

// CAP1188 レジスタ
#define REG_TOUCH_STATUS 0x03
#define REG_LED_LINKING 0x72
#define REG_LED_POLARITY 0x73

// グローバル変数
uint16_t prev_piano_touched = 0;
uint8_t  prev_drum_touched = 0;

uint8_t base_octave = 5;       // ピアノ初期オクターブ (C5 = 60)
uint8_t current_program = 0;   // ピアノ初期音色 (0: Grand Piano)

// GMドラム（Channel 10）ノート割り当て (8パッド分)
const uint8_t drum_notes[8] = {36, 38, 45, 47, 50, 42, 46, 49};

// --- MIDI送信ヘルパー ---
void sendMIDI(uint8_t status, uint8_t data1, uint8_t data2 = 255) {
  Serial1.write(status);
  Serial1.write(data1);
  if (data2 != 255) Serial1.write(data2);
}

// ピアノ用 (Channel 1)
void pianoNoteOn(uint8_t note, uint8_t velocity = 127) { sendMIDI(0x90, note, velocity); }
void pianoNoteOff(uint8_t note) { sendMIDI(0x80, note, 0); }
void setPianoProgram(uint8_t prog) { sendMIDI(0xC0, prog); }

// ドラム用 (Channel 10)
void drumNoteOn(uint8_t note, uint8_t velocity = 127) { sendMIDI(0x99, note, velocity); }
void drumNoteOff(uint8_t note) { sendMIDI(0x89, note, 0); }

// --- I2C 読み書き関数 ---
uint8_t readCapStatus(uint8_t addr) {
  Wire.beginTransmission(addr);
  Wire.write(REG_TOUCH_STATUS);
  Wire.endTransmission(false);
  Wire.requestFrom(addr, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0;
}

// --- 初期化 ---
void setup() {
  // MIDI (31250 bps)
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(31250);

  // I2C (400kHz)
  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  Wire.setClock(400000);

  // 全3基のCAP1188のLED設定を初期化
  uint8_t addrs[3] = {PIANO_1_ADDR, PIANO_2_ADDR, DRUM_ADDR};
  for (int i = 0; i < 3; i++) {
    Wire.beginTransmission(addrs[i]);
    Wire.write(REG_LED_POLARITY);
    Wire.write(0x00);
    Wire.endTransmission();

    Wire.beginTransmission(addrs[i]);
    Wire.write(REG_LED_LINKING);
    Wire.write(0xFF); // 全LEDを入力にリンク
    Wire.endTransmission();
  }

  delay(100);
  setPianoProgram(current_program);
}

// --- メインループ ---
void loop() {
  // 1. Piano HAT (16bit分) の読み出し
  uint8_t p1 = readCapStatus(PIANO_1_ADDR);
  uint8_t p2 = readCapStatus(PIANO_2_ADDR);
  uint16_t piano_touched = (uint16_t)p1 | ((uint16_t)p2 << 8);

  // 2. Drum HAT (8bit分) の読み出し
  uint8_t drum_touched = readCapStatus(DRUM_ADDR);

  // -------------------------------------------------------------
  // A. Piano HAT 処理
  // -------------------------------------------------------------
  if (piano_touched != prev_piano_touched) {
    for (int i = 0; i < 16; i++) {
      uint16_t mask = 1 << i;
      bool is_pressed = (piano_touched & mask) != 0;
      bool was_pressed = (prev_piano_touched & mask) != 0;

      if (is_pressed && !was_pressed) {
        if (i < 13) {
          pianoNoteOn((base_octave * 12) + i);
        } else if (i == 13 && base_octave > 1) {
          base_octave--; // オクターブ DOWN
        } else if (i == 14 && base_octave < 8) {
          base_octave++; // オクターブ UP
        } else if (i == 15) {
          current_program = (current_program + 1) % 128; // 音色変更
          setPianoProgram(current_program);
        }
      } else if (!is_pressed && was_pressed) {
        if (i < 13) pianoNoteOff((base_octave * 12) + i);
      }
    }
    prev_piano_touched = piano_touched;
  }

  // -------------------------------------------------------------
  // B. Drum HAT 処理
  // -------------------------------------------------------------
  if (drum_touched != prev_drum_touched) {
    for (int i = 0; i < 8; i++) {
      uint8_t mask = 1 << i;
      bool is_pressed = (drum_touched & mask) != 0;
      bool was_pressed = (prev_drum_touched & mask) != 0;

      if (is_pressed && !was_pressed) {
        drumNoteOn(drum_notes[i]);
      } else if (!is_pressed && was_pressed) {
        drumNoteOff(drum_notes[i]);
      }
    }
    prev_drum_touched = drum_touched;
  }

  delay(5); // ループ周波数を高めにして叩いた時のレイテンシーを抑制
}
