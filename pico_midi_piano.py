"""Minimal Raspberry Pi Pico + Piano HAT + M5Stack MIDI instrument."""

from __future__ import annotations

from dataclasses import dataclass

NOTE_BUTTON_COUNT = 13
OCTAVE_DOWN_BUTTON = 13
OCTAVE_UP_BUTTON = 14
INSTRUMENT_BUTTON = 15

DEFAULT_BASE_NOTE = 60
MIN_BASE_NOTE = 24
MAX_BASE_NOTE = 96
DEFAULT_VELOCITY = 100
DEFAULT_PROGRAMS = (0, 24, 40, 48, 60, 73)

CAP1188_ADDRESSES = (0x28, 0x2B)
CAP1188_MAIN_CONTROL = 0x00
CAP1188_INPUT_STATUS = 0x03
CAP1188_MULTITOUCH = 0x2A
CAP1188_STANDBY_CONFIG = 0x41
CAP1188_LED_LINKING = 0x72


@dataclass(frozen=True)
class PianoEvent:
    kind: str
    value: int


class MidiOut:
    """Send standard MIDI messages over a UART-like object."""

    def __init__(self, uart):
        self._uart = uart

    def note_on(self, note: int, velocity: int = DEFAULT_VELOCITY, channel: int = 0) -> None:
        self._write(0x90 | (channel & 0x0F), note & 0x7F, velocity & 0x7F)

    def note_off(self, note: int, velocity: int = 0, channel: int = 0) -> None:
        self._write(0x80 | (channel & 0x0F), note & 0x7F, velocity & 0x7F)

    def program_change(self, program: int, channel: int = 0) -> None:
        self._write(0xC0 | (channel & 0x0F), program & 0x7F)

    def _write(self, *values: int) -> None:
        self._uart.write(bytes(values))


class PianoHAT:
    """Read 16 Piano HAT touch inputs from two CAP1188 sensors over I2C."""

    def __init__(self, i2c, addresses=CAP1188_ADDRESSES):
        self._i2c = i2c
        self._addresses = tuple(addresses)

    def configure(self) -> None:
        for address in self._addresses:
            self._write_register(address, CAP1188_MULTITOUCH, 0x00)
            self._write_register(address, CAP1188_LED_LINKING, 0xFF)
            self._write_register(address, CAP1188_STANDBY_CONFIG, 0x30)

    def read_pressed_indices(self) -> list[int]:
        pressed = []
        for chip_index, address in enumerate(self._addresses):
            touched = self._read_register(address, CAP1188_INPUT_STATUS)
            if touched:
                main = self._read_register(address, CAP1188_MAIN_CONTROL)
                self._write_register(address, CAP1188_MAIN_CONTROL, main & ~0x01)

            offset = chip_index * 8
            for bit in range(8):
                if touched & (1 << bit):
                    pressed.append(offset + bit)
        return pressed

    def _read_register(self, address: int, register: int) -> int:
        return self._i2c.readfrom_mem(address, register, 1)[0]

    def _write_register(self, address: int, register: int, value: int) -> None:
        self._i2c.writeto_mem(address, register, bytes((value,)))


class PicoMidiPiano:
    """Map Piano HAT button edges to MIDI note and program changes."""

    def __init__(
        self,
        keyboard: PianoHAT,
        midi_out: MidiOut,
        *,
        base_note: int = DEFAULT_BASE_NOTE,
        min_base_note: int = MIN_BASE_NOTE,
        max_base_note: int = MAX_BASE_NOTE,
        velocity: int = DEFAULT_VELOCITY,
        channel: int = 0,
        programs=DEFAULT_PROGRAMS,
    ):
        self._keyboard = keyboard
        self._midi_out = midi_out
        self.base_note = base_note
        self.min_base_note = min_base_note
        self.max_base_note = max_base_note
        self.velocity = velocity
        self.channel = channel
        self.programs = tuple(programs) or (0,)
        self.program_index = 0
        self._pressed_buttons = set()
        self._active_notes = {}

    @property
    def current_program(self) -> int:
        return self.programs[self.program_index]

    def send_current_program(self) -> int:
        self._midi_out.program_change(self.current_program, self.channel)
        return self.current_program

    def poll(self) -> list[PianoEvent]:
        return self.sync_pressed_indices(self._keyboard.read_pressed_indices())

    def sync_pressed_indices(self, pressed_indices) -> list[PianoEvent]:
        pressed = set(pressed_indices)
        newly_pressed = pressed - self._pressed_buttons
        newly_released = self._pressed_buttons - pressed
        events = []

        for button in sorted(newly_released):
            if button < NOTE_BUTTON_COUNT and button in self._active_notes:
                note = self._active_notes.pop(button)
                self._midi_out.note_off(note, channel=self.channel)
                events.append(PianoEvent("note_off", note))

        for button in sorted(newly_pressed):
            if button == OCTAVE_DOWN_BUTTON:
                self.base_note = max(self.min_base_note, self.base_note - 12)
                events.append(PianoEvent("octave_down", self.base_note))
            elif button == OCTAVE_UP_BUTTON:
                self.base_note = min(self.max_base_note, self.base_note + 12)
                events.append(PianoEvent("octave_up", self.base_note))
            elif button == INSTRUMENT_BUTTON:
                self.program_index = (self.program_index + 1) % len(self.programs)
                program = self.current_program
                self._midi_out.program_change(program, self.channel)
                events.append(PianoEvent("program_change", program))

        for button in sorted(newly_pressed):
            if button < NOTE_BUTTON_COUNT:
                note = self.base_note + button
                self._active_notes[button] = note
                self._midi_out.note_on(note, self.velocity, self.channel)
                events.append(PianoEvent("note_on", note))

        self._pressed_buttons = pressed
        return events
