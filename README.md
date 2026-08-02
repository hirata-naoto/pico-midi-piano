# pico-midi-piano

Raspberry Pi Pico に **Piano HAT** と **Drum HAT** を同時接続し、M5Stack Unit MIDI (SAM2695) に UART MIDI を送る Arduino スケッチです。

## 構成

- **Raspberry Pi Pico**: タッチ入力の読み取りと MIDI 送信
- **Piano HAT (CAP1188 x2)**: 16 キー
  - 0-12: ピアノ鍵盤（C〜上のC）
  - 13: octave down
  - 14: octave up
  - 15: instrument change（Program Change）
- **Drum HAT (CAP1188 x1)**: 8 パッド
  - GM ドラムノート割り当て: `36, 38, 45, 47, 50, 42, 46, 49`
  - パッドごとの音色
    - Pad 0: `36` Bass Drum 1
    - Pad 1: `38` Acoustic Snare
    - Pad 2: `45` Low Tom
    - Pad 3: `47` Low-Mid Tom
    - Pad 4: `50` High Tom
    - Pad 5: `42` Closed Hi-Hat
    - Pad 6: `46` Open Hi-Hat
    - Pad 7: `49` Crash Cymbal 1
- **M5Stack Unit MIDI (SAM2695)**: MIDI 音源

## I2C アドレス

- Piano HAT 前半: `0x28`（Pad 0〜7）
- Piano HAT 後半: `0x2B`（Pad 8〜15）
- Drum HAT: `0x2C`（Pad 0〜7）

## 配線

### HAT群 → Pico（I2C）

- Pico `5V` → 各 HAT の `5V`
- Pico `3V3` → 各 HAT の `3V3`
- Pico `GND` → 各 HAT の `GND`
- Pico `GP4` → SDA
- Pico `GP5` → SCL

### Pico → M5Stack Unit MIDI（UART）

- Pico `GP0` (UART1 TX) → Unit MIDI `RX`
- Pico `GP1` (UART1 RX) → Unit MIDI `TX`（未使用でも接続可）
- Pico `VSYS / 5V` → Unit MIDI `5V`
- Pico `GND` → Unit MIDI `GND`

> Unit MIDI は **Separate mode**、ボーレート **31250 bps**（標準 MIDI）を想定しています。

## MIDI 動作

- ピアノ: **Channel 1**（Note On/Off, Program Change）
- ドラム: **Channel 10**（Note On/Off）
- HAT 側 LED は CAP1188 の LED Link mode でタッチ入力に連動
- ループ遅延は `5ms`（低レイテンシー向け）

## ファイル

- `/home/runner/work/pico-midi-piano/pico-midi-piano/main.ino`
  - Piano HAT + Drum HAT の入力処理と MIDI 出力

## 書き込み・実行

Arduino IDE / arduino-cli で Raspberry Pi Pico 向けに `main.ino` を書き込んで実行してください。