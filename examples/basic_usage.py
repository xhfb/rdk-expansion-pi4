"""Read board sensors and demonstrate safe, explicit actuation."""

from __future__ import annotations

from rdk_expansion import ExpansionBoard


def main() -> None:
    with ExpansionBoard.open() as board:
        for capability in board.capabilities():
            print(capability)

        print("ADC AIN0:", board.adc.read(0))
        print("Input power:", board.power.read())

        if board.buttons.key0.is_pressed:
            board.buzzer.beep(0.1)

        # Load actuation is intentionally explicit. Context exit restores the
        # relay safe state and stops both servo pulse trains.
        board.relays[0].on()
        board.relays[0].off()
        board.servos[0].set_angle(90)
        board.servos[0].disable()


if __name__ == "__main__":
    main()
