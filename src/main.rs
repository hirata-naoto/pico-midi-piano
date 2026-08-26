#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_rp::bind_interrupts;
use embassy_rp::i2c::{self, I2c};
use embassy_rp::peripherals::{I2C1, UART0};
use embassy_rp::uart::{self, Uart};
use embassy_time::{Duration, Ticker, Timer};
use embedded_hal_async::i2c::I2c as _; // write/read/write_read の非同期traitを使うため
use embedded_io_async::Write;          // uart.write() のため
use {defmt_rtt as _, panic_probe as _};

// --- I2C アドレス定義 ---
const PIANO_1_ADDR: u8 = 0x28; // Piano HAT 前半 (Pad 0〜7)
const PIANO_2_ADDR: u8 = 0x2B; // Piano HAT 後半 (Pad 8〜15)
const DRUM_ADDR: u8 = 0x2C; // Drum HAT (Pad 0〜7)

// CAP1188 レジスタ
const REG_MAIN_CONTROL: u8 = 0x00;
const REG_TOUCH_STATUS: u8 = 0x03;
const REG_MULTITOUCH: u8 = 0x2A;
const REG_STANDBY_CONFIG: u8 = 0x41;
const REG_LED_LINKING: u8 = 0x72;
const REG_LED_POLARITY: u8 = 0x73;

// GMドラム（Channel 10）ノート割り当て (8パッド分)
const DRUM_NOTES: [u8; 8] = [36, 38, 45, 47, 50, 42, 46, 49];
// 36: Bass Drum 1, 38: Acoustic Snare, 45: Low Tom, 47: Low-Mid Tom
// 50: High Tom, 42: Closed Hi-Hat, 46: Open Hi-Hat, 49: Crash Cymbal 1

// 割り込みハンドラのバインド
// (元コードの Wire1 = I2C1, Serial1 = UART0 に対応)
bind_interrupts!(struct Irqs {
    I2C1_IRQ => i2c::InterruptHandler<I2C1>;
    UART0_IRQ => uart::InterruptHandler<UART0>;
});

type MidiUart = Uart<'static, UART0, uart::Async>;
type CapI2c = I2c<'static, I2C1, i2c::Async>;

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_rp::init(Default::default());

    // I2C (400kHz) — SDA=GP4, SCL=GP5
    let mut i2c_cfg = i2c::Config::default();
    i2c_cfg.frequency = 400_000;
    let mut i2c: CapI2c = I2c::new_async(p.I2C1, p.PIN_5, p.PIN_4, Irqs, i2c_cfg);

    // MIDI UART (31250bps) — TX=GP0, RX=GP1
    let mut uart_cfg = uart::Config::default();
    uart_cfg.baudrate = 31250;
    let mut midi_uart: MidiUart = Uart::new(
        p.UART0, p.PIN_0, p.PIN_1, Irqs, p.DMA_CH0, p.DMA_CH1, uart_cfg,
    );

    // 状態
    let mut prev_piano_touched: u16 = 0;
    let mut prev_drum_touched: u8 = 0;
    let mut base_octave: u8 = 5; // ピアノ初期オクターブ (C5 = 60)
    let mut current_program: u8 = 0; // ピアノ初期音色 (0: Grand Piano)

    // 全3基のCAP1188のLED設定を初期化
    let addrs = [PIANO_1_ADDR, PIANO_2_ADDR, DRUM_ADDR];
    for &addr in &addrs {
        write_cap_reg(&mut i2c, addr, REG_MULTITOUCH, 0x00).await; // 無制限マルチタッチ
        write_cap_reg(&mut i2c, addr, REG_STANDBY_CONFIG, 0x30).await; // スタンバイ設定
        write_cap_reg(&mut i2c, addr, REG_LED_POLARITY, 0x00).await;
        write_cap_reg(&mut i2c, addr, REG_LED_LINKING, 0xFF).await; // 全LEDを入力にリンク
        setup_sensitivity(&mut i2c, addr).await; 
    }

    Timer::after(Duration::from_millis(100)).await;
    set_piano_program(&mut midi_uart, current_program).await;
    defmt::info!("Initial program: {}", current_program);

    // 固定周期でポーリングするためのTicker。
    let mut ticker = Ticker::every(Duration::from_millis(5));

    loop {
        // 1. Piano HAT (16bit分) の読み出し
        let p1 = read_cap_status(&mut i2c, PIANO_1_ADDR).await;
        let p2 = read_cap_status(&mut i2c, PIANO_2_ADDR).await;
        let piano_touched: u16 = (p1 as u16) | ((p2 as u16) << 8);

        // 2. Drum HAT (8bit分) の読み出し
        let drum_touched = read_cap_status(&mut i2c, DRUM_ADDR).await;

        // -------------------------------------------------------------
        // A. Piano HAT 処理
        // -------------------------------------------------------------
        if piano_touched != prev_piano_touched {
            for i in 0u8..16 {
                let mask = 1u16 << i;
                let is_pressed = (piano_touched & mask) != 0;
                let was_pressed = (prev_piano_touched & mask) != 0;

                if is_pressed && !was_pressed {
                    if i < 13 {
                        let note = base_octave * 12 + i;
                        piano_note_on(&mut midi_uart, note, 127).await;
                        defmt::info!("[Piano ON] key={} note={}", i, note);
                    } else if i == 13 && base_octave > 1 {
                        base_octave -= 1; // オクターブ DOWN
                        defmt::info!("[Octave] {}", base_octave);
                    } else if i == 14 && base_octave < 8 {
                        base_octave += 1; // オクターブ UP
                        defmt::info!("[Octave] {}", base_octave);
                    } else if i == 15 {
                        current_program = (current_program + 1) % 128; // 音色変更
                        set_piano_program(&mut midi_uart, current_program).await;
                        defmt::info!("[Program] {}", current_program);
                    }
                } else if !is_pressed && was_pressed && i < 13 {
                    let note = base_octave * 12 + i;
                    piano_note_off(&mut midi_uart, note).await;
                    defmt::info!("[Piano OFF] key={} note={}", i, note);
                }
            }
            prev_piano_touched = piano_touched;
        }

        // -------------------------------------------------------------
        // B. Drum HAT 処理
        // -------------------------------------------------------------
        if drum_touched != prev_drum_touched {
            for i in 0u8..8 {
                let mask = 1u8 << i;
                let is_pressed = (drum_touched & mask) != 0;
                let was_pressed = (prev_drum_touched & mask) != 0;
                let note = DRUM_NOTES[i as usize];

                if is_pressed && !was_pressed {
                    drum_note_on(&mut midi_uart, note, 127).await;
                    defmt::info!("[Drum ON] pad={} note={}", i, note);
                } else if !is_pressed && was_pressed {
                    drum_note_off(&mut midi_uart, note).await;
                    defmt::info!("[Drum OFF] pad={} note={}", i, note);
                }
            }
            prev_drum_touched = drum_touched;
        }

        ticker.next().await; // 次の5ms周期まで待機
    }
}

// --- MIDI送信ヘルパー ---
async fn send_midi(uart: &mut MidiUart, status: u8, data1: u8, data2: Option<u8>) {
    let _ = uart.write(&[status, data1]).await;
    if let Some(d2) = data2 {
        let _ = uart.write(&[d2]).await;
    }
}

// ピアノ用 (Channel 1)
async fn piano_note_on(uart: &mut MidiUart, note: u8, velocity: u8) {
    send_midi(uart, 0x90, note, Some(velocity)).await;
}
async fn piano_note_off(uart: &mut MidiUart, note: u8) {
    send_midi(uart, 0x80, note, Some(0)).await;
}
async fn set_piano_program(uart: &mut MidiUart, prog: u8) {
    send_midi(uart, 0xC0, prog, None).await;
}

// ドラム用 (Channel 10)
async fn drum_note_on(uart: &mut MidiUart, note: u8, velocity: u8) {
    send_midi(uart, 0x99, note, Some(velocity)).await;
}
async fn drum_note_off(uart: &mut MidiUart, note: u8) {
    send_midi(uart, 0x89, note, Some(0)).await;
}

// --- I2C 読み書き関数 ---
async fn read_cap_reg(i2c: &mut CapI2c, addr: u8, reg: u8) -> u8 {
    let mut buf = [0u8; 1];
    let _ = i2c.write_read(addr, &[reg], &mut buf).await;
    buf[0]
}

async fn write_cap_reg(i2c: &mut CapI2c, addr: u8, reg: u8, value: u8) {
    let _ = i2c.write(addr, &[reg, value]).await;
}

async fn read_cap_status(i2c: &mut CapI2c, addr: u8) -> u8 {
    let touched = read_cap_reg(i2c, addr, REG_TOUCH_STATUS).await;

    // 無条件にINTフラグをクリア
    let main_ctrl = read_cap_reg(i2c, addr, REG_MAIN_CONTROL).await;
    write_cap_reg(i2c, addr, REG_MAIN_CONTROL, main_ctrl & !0x01).await;

    touched
}

async fn setup_sensitivity(i2c: &mut CapI2c, addr: u8) {
    // チャンネル0〜7のタッチしきい値を下げて高感度化（Pimoroni公式相当）
    for ch in 0u8..8 {
        write_cap_reg(i2c, addr, 0x30 + ch, 0x06).await;
    }
    // 全体の感度倍率（Sensitivity Control, 0x1F）: 2倍感度
    write_cap_reg(i2c, addr, 0x1F, 0b0110_0000).await;
    // サンプリング設定(0x24): 1サンプル/測定, 高速サイクル
    write_cap_reg(i2c, addr, 0x24, 0x00).await;
}
