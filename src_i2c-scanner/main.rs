#![no_std]
#![no_main]

use defmt::*;
use embassy_executor::Spawner;
use embassy_rp::{bind_interrupts};
use embassy_rp::i2c::{self, I2c};
use embassy_rp::peripherals::{I2C0};
use embassy_time::{Duration, Ticker, Timer};
use embedded_hal_async::i2c::I2c as _; // write/read/write_read の非同期traitを使うため
use {defmt_rtt as _, panic_probe as _};

// 割り込みハンドラのバインド
bind_interrupts!(struct Irqs {
    I2C0_IRQ => i2c::InterruptHandler<I2C0>;
});
const SCAN_START: u8 = 0x08;
const SCAN_END: u8 = 0x77;


#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_rp::init(Default::default());

    // I2C (100kHz) — SDA=GP4, SCL=GP5
    let mut i2c_cfg = i2c::Config::default();
    i2c_cfg.frequency = 100_000;
    let mut i2c = I2c::new_async(p.I2C0, p.PIN_5, p.PIN_4, Irqs, i2c_cfg);

    info!("I2C Scan Start");
    for addr in SCAN_START..=SCAN_END {
        let mut buf = [0u8; 1];
        match i2c.write_read(addr, &[], &mut buf).await {
            Ok(_) => {
                info!("Found I2C device at address: 0x{:02X}", addr);
            }
            Err(_) => {
                // No device found at this address
            }
        }
    }
    info!("I2C Scan End");
}
