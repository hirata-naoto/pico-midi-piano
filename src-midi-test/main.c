#![no_std]
#![no_main]

use core::num::FpCategory::Infinite;

use defmt::*;
use embassy_executor::Spawner;
use embassy_rp::{bind_interrupts, dma};
use embassy_rp::i2c::{self, I2c};
use embassy_rp::peripherals::{I2C0, UART0, DMA_CH0};
use embassy_rp::uart::{self, UartTx};
use embassy_time::{Duration, Ticker, Timer};
use embedded_hal_async::i2c::I2c as _; // write/read/write_read の非同期traitを使うため
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
bind_interrupts!(struct Irqs {
    UART0_IRQ => uart::InterruptHandler<UART0>;
    DMA_IRQ_0 => dma::InterruptHandler<DMA_CH0>;
});
type MidiUart = UartTx<'static, uart::Async>;
type CapI2c = I2c<'static, I2C0, i2c::Async>;

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_rp::init(Default::default());

    // MIDI UART (31250bps) — TX=GP0, RX=GP1
    let mut uart_cfg = uart::Config::default();
    uart_cfg.baudrate = 31250; // MIDI標準は31250bpsですが、ここでは115200bpsで動作させます
    let mut midi_uart: MidiUart = UartTx::new(
        p.UART0, p.PIN_0, p.DMA_CH0, Irqs, uart_cfg,
    );

    info!("MIDI UART initialized at 31250 bps");
    Timer::after(Duration::from_millis(500)).await; // UART初期化待ち

    let _ = midi_uart.write(&[0xC0, 00]).await; // Program Change: Piano 0
    let _ = midi_uart.write(&[0xB0, 7, 127]).await; // Control Change: Volume (7) to 100
    info!("Sent Program Change and Volume Control");

    let mut pg = 0;

    loop {
        let _ = midi_uart.write(&[0x90, 60, 100]).await;
        info!("Sent MIDI Note On: 60 (Middle C) with velocity 100");
        Timer::after(Duration::from_millis(1000)).await; // 1000ms待

        let _ = midi_uart.write(&[0x80, 60, 0]).await;
        info!("Sent MIDI Note Off: 60 (Middle C)");
        Timer::after(Duration::from_millis(1000)).await; // 1000ms待

        pg = (pg + 1) % 128;
        let _ = midi_uart.write(&[0xC0, pg]).await; // Program Change
        info!("Sent Program Change: {}", pg);
    }
}
