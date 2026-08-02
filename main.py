"""MicroPython entry point for the Pico MIDI piano."""

from pico_midi_piano import MidiOut, PianoHAT, PicoMidiPiano

try:
    from machine import I2C, Pin, UART
    import time
except ImportError as exc:  # pragma: no cover - this file is for MicroPython hardware
    raise SystemExit("main.py must be executed on a Raspberry Pi Pico with MicroPython.") from exc


def create_instrument(
    *,
    i2c_id: int = 0,
    sda_pin: int = 0,
    scl_pin: int = 1,
    uart_id: int = 0,
    tx_pin: int = 12,
    uart_baudrate: int = 31250,
) -> PicoMidiPiano:
    i2c = I2C(i2c_id, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=100_000)
    piano_hat = PianoHAT(i2c)
    piano_hat.configure()

    uart = UART(uart_id, baudrate=uart_baudrate, tx=Pin(tx_pin))
    midi_out = MidiOut(uart)

    instrument = PicoMidiPiano(piano_hat, midi_out)
    instrument.send_current_program()
    return instrument


def main(poll_interval_ms: int = 20) -> None:
    instrument = create_instrument()

    while True:
        instrument.poll()
        time.sleep_ms(poll_interval_ms)


if __name__ == "__main__":
    main()
