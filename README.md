# pico-midi-piano

Raspberry Pi Pico と Piano HAT を鍵盤にして、M5Stack Unit MIDI (SAM2695) を音源として鳴らすための最小構成です。

## 構成

- **Raspberry Pi Pico**: キー入力の読み取りと MIDI 送信
- **Piano HAT**: 16 個のタッチキー
  - 0-12: C 〜 上の C
  - 13: octave down
  - 14: octave up
  - 15: instrument change
- **M5Stack Unit MIDI (SAM2695)**: UART MIDI 音源

## 配線

### Piano HAT → Pico

Piano HAT は 2 個の CAP1188 (`0x28`, `0x2b`) を I2C で読みます。

- Pico `GP0` → Piano HAT `SDA`
- Pico `GP1` → Piano HAT `SCL`
- Pico `3V3` → Piano HAT `3V3`
- Pico `GND` → Piano HAT `GND`

### Pico → M5Stack Unit MIDI

- Pico `GP12` (UART TX) → Unit MIDI `RX`
- Pico `VSYS / 5V` → Unit MIDI `5V`
- Pico `GND` → Unit MIDI `GND`

> Unit MIDI は **Separate mode** にして、UART 31250bps の標準 MIDI を受ける想定です。

## ファイル

- `/home/runner/work/pico-midi-piano/pico-midi-piano/pico_midi_piano.py`
  - Piano HAT 入力、MIDI 出力、状態管理
- `/home/runner/work/pico-midi-piano/pico-midi-piano/main.py`
  - Pico 上の実行エントリポイント
- `/home/runner/work/pico-midi-piano/pico-midi-piano/tests/test_pico_midi_piano.py`
  - PC 上で回せるユニットテスト

## Pico での実行

1. Pico に MicroPython を書き込みます。
2. `main.py` と `pico_midi_piano.py` を Pico にコピーします。

例:

```bash
mpremote cp /home/runner/work/pico-midi-piano/pico-midi-piano/pico_midi_piano.py :
mpremote cp /home/runner/work/pico-midi-piano/pico-midi-piano/main.py :
mpremote reset
```

起動すると、Piano HAT のタッチ状態を 20ms ごとにポーリングし、押したキーに対応する Note On / Note Off を Unit MIDI に送ります。

## ローカルテスト

PC 上ではハードウェア不要のロジックテストだけ実行できます。

```bash
cd /home/runner/work/pico-midi-piano/pico-midi-piano
python -m unittest discover -s tests -v
```