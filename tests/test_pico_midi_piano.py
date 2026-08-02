import unittest

from pico_midi_piano import (
    CAP1188_ADDRESSES,
    CAP1188_INPUT_STATUS,
    CAP1188_LED_LINKING,
    CAP1188_MAIN_CONTROL,
    CAP1188_MULTITOUCH,
    CAP1188_STANDBY_CONFIG,
    INSTRUMENT_BUTTON,
    MidiOut,
    OCTAVE_UP_BUTTON,
    PianoHAT,
    PicoMidiPiano,
)


class FakeUart:
    def __init__(self):
        self.messages = []

    def write(self, payload):
        self.messages.append(bytes(payload))


class FakeI2C:
    def __init__(self, registers):
        self.registers = dict(registers)
        self.writes = []

    def readfrom_mem(self, address, register, size):
        return bytes((self.registers.get((address, register), 0),))

    def writeto_mem(self, address, register, payload):
        value = payload[0]
        self.registers[(address, register)] = value
        self.writes.append((address, register, value))


class PicoMidiPianoTests(unittest.TestCase):
    def test_note_on_and_note_off_are_sent(self):
        uart = FakeUart()
        instrument = PicoMidiPiano(keyboard=None, midi_out=MidiOut(uart))

        instrument.sync_pressed_indices([0])
        instrument.sync_pressed_indices([])

        self.assertEqual(
            uart.messages,
            [
                bytes((0x90, 60, 100)),
                bytes((0x80, 60, 0)),
            ],
        )

    def test_octave_up_changes_new_note_pitch(self):
        uart = FakeUart()
        instrument = PicoMidiPiano(keyboard=None, midi_out=MidiOut(uart))

        events = instrument.sync_pressed_indices([OCTAVE_UP_BUTTON])
        instrument.sync_pressed_indices([])
        instrument.sync_pressed_indices([0])

        self.assertEqual(events[0].kind, "octave_up")
        self.assertEqual(events[0].value, 72)
        self.assertEqual(uart.messages[-1], bytes((0x90, 72, 100)))

    def test_program_button_cycles_instruments(self):
        uart = FakeUart()
        instrument = PicoMidiPiano(keyboard=None, midi_out=MidiOut(uart), programs=(0, 24, 40))

        events = instrument.sync_pressed_indices([INSTRUMENT_BUTTON])

        self.assertEqual(events[0].kind, "program_change")
        self.assertEqual(events[0].value, 24)
        self.assertEqual(uart.messages, [bytes((0xC0, 24))])

    def test_held_note_uses_original_pitch_for_note_off(self):
        uart = FakeUart()
        instrument = PicoMidiPiano(keyboard=None, midi_out=MidiOut(uart))

        instrument.sync_pressed_indices([0])
        instrument.sync_pressed_indices([0, OCTAVE_UP_BUTTON])
        instrument.sync_pressed_indices([0])
        instrument.sync_pressed_indices([])

        self.assertEqual(uart.messages[-1], bytes((0x80, 60, 0)))


class PianoHATTests(unittest.TestCase):
    def test_configure_writes_expected_registers(self):
        i2c = FakeI2C({})
        piano_hat = PianoHAT(i2c)

        piano_hat.configure()

        expected = {
            (CAP1188_ADDRESSES[0], CAP1188_MULTITOUCH, 0x00),
            (CAP1188_ADDRESSES[0], CAP1188_LED_LINKING, 0xFF),
            (CAP1188_ADDRESSES[0], CAP1188_STANDBY_CONFIG, 0x30),
            (CAP1188_ADDRESSES[1], CAP1188_MULTITOUCH, 0x00),
            (CAP1188_ADDRESSES[1], CAP1188_LED_LINKING, 0xFF),
            (CAP1188_ADDRESSES[1], CAP1188_STANDBY_CONFIG, 0x30),
        }
        self.assertEqual(set(i2c.writes), expected)

    def test_pressed_indices_are_combined_from_both_sensors(self):
        i2c = FakeI2C(
            {
                (CAP1188_ADDRESSES[0], CAP1188_INPUT_STATUS): 0b00000001,
                (CAP1188_ADDRESSES[0], CAP1188_MAIN_CONTROL): 0b00000001,
                (CAP1188_ADDRESSES[1], CAP1188_INPUT_STATUS): 0b00000100,
                (CAP1188_ADDRESSES[1], CAP1188_MAIN_CONTROL): 0b00000001,
            }
        )
        piano_hat = PianoHAT(i2c)

        pressed = piano_hat.read_pressed_indices()

        self.assertEqual(pressed, [0, 10])
        self.assertIn((CAP1188_ADDRESSES[0], CAP1188_MAIN_CONTROL, 0), i2c.writes)
        self.assertIn((CAP1188_ADDRESSES[1], CAP1188_MAIN_CONTROL, 0), i2c.writes)


if __name__ == "__main__":
    unittest.main()
