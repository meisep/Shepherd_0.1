from pymeasure.instruments import Instrument, SCPIMixin
from pymeasure.instruments.validators import strict_discrete_set, strict_range
import time


class BNC765(SCPIMixin, Instrument):
    """
    Berkeley Nucleonics 765 Pulse Generator

    Based on SCPI commands from Model 765 Programmer Manual [6]
    """

    def __init__(self, adapter, name="BNC765 Pulse Generator", **kwargs):
        super().__init__(
            adapter,
            name,
            # includeSCPI=True,
            **kwargs
        )
        # Create channel objects
        self.ch1 = BNC765Channel(self, 1)
        self.ch2 = BNC765Channel(self, 2)
        self.ch3 = BNC765Channel(self, 3)
        self.ch4 = BNC765Channel(self, 4)

    # Trigger mode
    trigger_mode = Instrument.control(
        "TRIGGER:MODE?", "TRIGGER:MODE %s",
        """Control trigger mode (BURST, CONTINUOUS)""",
        validator=strict_discrete_set,
        values=['BURST', 'CONTINUOUS', 'CONT', 'BURS']
    )

    trigger_source = Instrument.control(
        "TRIGGER:SOURCE?", "TRIGGER:SOURCE %s",
        """Control trigger source (MANUAL, EXTERNAL, etc.)""",
        validator=strict_discrete_set,
        values=['MANUAL', 'EXTERNAL', 'EXT', 'MAN']
    )

    # Trigger output
    trigger_output_amplitude = Instrument.control(
        "TRIGGER:OUTPUT:AMPLITUDE?", "TRIGGER:OUTPUT:AMPLITUDE %g",
        """Control trigger output amplitude in Volts (0.9-5V)""",
        validator=strict_range,
        values=[0.9, 5.0]
    )

    trigger_output_polarity = Instrument.control(
        "TRIGGER:OUTPUT:POLARITY?", "TRIGGER:OUTPUT:POLARITY %s",
        """Control trigger output polarity""",
        validator=strict_discrete_set,
        values=['POSITIVE', 'NEGATIVE']
    )

    trigger_output_delay = Instrument.control(
        "TRIGGER:OUTPUT:DELAY?", "TRIGGER:OUTPUT:DELAY %g",
        """Trigger output delay in seconds"""
    )

    def start(self):
        """Start pulse generator - arms instrument for trigger [6]"""
        self.write("PULSEGENCONTROL:START")
        time.sleep(0.5)

    def stop(self):
        """Stop pulse generator [6]"""
        self.write("PULSEGENCONTROL:STOP")

    def trigger(self):
        """Send software trigger"""
        self.write("*TRG")

    def reset(self):
        """Reset instrument"""
        self.write("*RST")
        time.sleep(2)

    def get_status(self):
        """Get instrument status [6]"""
        return self.ask("PULSEGENCONTROL:STATUS?")

    def get_channel_count(self):
        """Get number of output channels available (Model 765 Rev. B only) [6]"""
        try:
            return int(self.ask("PULSEGENCONTROL:CONFIGURE:CNUMBER?"))
        except:
            return 4  # Default for Rev. A

    def setup_burst_mode(self, channel=1):
        """Convenience method to setup basic burst mode"""
        ch = getattr(self, f'ch{channel}')
        ch.output_state = True
        self.trigger_mode = 'BURST'
        self.trigger_source = 'MANUAL'
        ch.burst_ncycles = 1
        self.start()

    def shutdown(self):
        """Safe shutdown - stop all channels"""
        try:
            self.stop()
            for i in [1, 2, 3, 4]:
                ch = getattr(self, f'ch{i}')
                ch.output_state = False
        except:
            pass
        finally:
            if hasattr(self, 'adapter') and self.adapter:
                try:
                    self.adapter.close()
                except:
                    pass


class BNC765Channel:
    """
    Represents a single channel of the BNC765

    SCPI format: [SOURce[1|2|3|4]] for channel commands [6]
    """

    def __init__(self, instrument, channel):
        self.instrument = instrument
        self.channel = channel
        self._prefix = f"SOURCE{channel}"

    # Output state
    @property
    def output_state(self):
        """Get output state (True=ON, False=OFF)"""
        return bool(int(self.instrument.ask(f"OUTPUT{self.channel}:STATE?")))

    @output_state.setter
    def output_state(self, value):
        """Set output state (True=ON, False=OFF)"""
        state = "ON" if value else "OFF"
        self.instrument.write(f"OUTPUT{self.channel}:STATE {state}")
        time.sleep(0.1)

    # Voltage
    @property
    def voltage_level(self):
        """Get voltage level in Volts"""
        return float(self.instrument.ask(f"{self._prefix}:VOLTAGE:LEVEL?"))

    @voltage_level.setter
    def voltage_level(self, value):
        """Set voltage level in Volts"""
        if not 0 <= value <= 5:
            raise ValueError("Voltage must be 0-5V")
        self.instrument.write(f"{self._prefix}:VOLTAGE:LEVEL {value}")

    @property
    def voltage_offset(self):
        """Get voltage offset in Volts"""
        return float(self.instrument.ask(f"{self._prefix}:VOLTAGE:OFFSET?"))

    @voltage_offset.setter
    def voltage_offset(self, value):
        """Set voltage offset in Volts"""
        self.instrument.write(f"{self._prefix}:VOLTAGE:OFFSET {value}")

    # Individual pulse parameters - format: [SOURce[1|2|3|4]]:PULSe[1|2|3|4] [6]
    def set_pulse_width(self, pulse_num, value):
        """Set width for specific pulse (1-4) in seconds [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        self.instrument.write(f"{self._prefix}:PULSE{pulse_num}:WIDTH {value}")

    def get_pulse_width(self, pulse_num):
        """Get width for specific pulse (1-4) in seconds [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        return float(self.instrument.ask(f"{self._prefix}:PULSE{pulse_num}:WIDTH?"))

    def set_pulse_delay(self, pulse_num, value):
        """Set delay for specific pulse (1-4) in seconds [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        self.instrument.write(f"{self._prefix}:PULSE{pulse_num}:DELAY {value}")

    def get_pulse_delay(self, pulse_num):
        """Get delay for specific pulse (1-4) in seconds [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        return float(self.instrument.ask(f"{self._prefix}:PULSE{pulse_num}:DELAY?"))

    def set_pulse_phase(self, pulse_num, value):
        """Set phase for specific pulse (1-4) [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        self.instrument.write(f"{self._prefix}:PULSE{pulse_num}:PHASE {value}")

    def get_pulse_phase(self, pulse_num):
        """Get phase for specific pulse (1-4) [6]"""
        if pulse_num not in [1, 2, 3, 4]:
            raise ValueError("pulse_num must be 1-4")
        return float(self.instrument.ask(f"{self._prefix}:PULSE{pulse_num}:PHASE?"))

    # Legacy single-pulse properties (for backward compatibility)
    @property
    def pulse_width(self):
        """Get pulse 1 width in seconds"""
        return self.get_pulse_width(1)

    @pulse_width.setter
    def pulse_width(self, value):
        """Set pulse 1 width in seconds"""
        self.set_pulse_width(1, value)

    @property
    def pulse_delay(self):
        """Get pulse 1 delay in seconds"""
        return self.get_pulse_delay(1)

    @pulse_delay.setter
    def pulse_delay(self, value):
        """Set pulse 1 delay in seconds"""
        self.set_pulse_delay(1, value)

    @property
    def frequency(self):
        """Get frequency in Hz"""
        return float(self.instrument.ask(f"{self._prefix}:FREQUENCY?"))

    @frequency.setter
    def frequency(self, value):
        """Set frequency in Hz"""
        self.instrument.write(f"{self._prefix}:FREQUENCY {value}")

    @property
    def period(self):
        """Get period in seconds"""
        return float(self.instrument.ask(f"{self._prefix}:PERIOD?"))

    @period.setter
    def period(self, value):
        """Set period in seconds"""
        self.instrument.write(f"{self._prefix}:PERIOD {value}")

    # Polarity
    @property
    def inverted(self):
        """Get invert state (True=inverted, False=normal)"""
        return bool(int(self.instrument.ask(f"{self._prefix}:INV?")))

    @inverted.setter
    def inverted(self, value):
        """Set invert state (True=inverted, False=normal)"""
        state = "ON" if value else "OFF"
        self.instrument.write(f"{self._prefix}:INV {state}")

    # Output impedance - format: SOUR[N]:LOAD:IMP [6]
    @property
    def load_impedance(self):
        """Get load impedance setting"""
        return self.instrument.ask(f"SOUR{self.channel}:LOAD:IMP?").strip()

    @load_impedance.setter
    def load_impedance(self, value):
        """Set load impedance (50, 'INF', etc.)"""
        self.instrument.write(f"SOUR{self.channel}:LOAD:IMP {value}")

    # Burst mode
    @property
    def burst_ncycles(self):
        """Get burst cycle count"""
        return int(float(self.instrument.ask(f"{self._prefix}:BURST:NCYCLES?")))

    @burst_ncycles.setter
    def burst_ncycles(self, value):
        """Set burst cycle count"""
        self.instrument.write(f"{self._prefix}:BURST:NCYCLES {value}")

    # Pulse mode
    @property
    def pulse_mode(self):
        """Get pulse mode (SIN, DOU, TRI, QUAD)"""
        return self.instrument.ask(f"OUTPUT{self.channel}:PULSE:MODE?").strip()

    @pulse_mode.setter
    def pulse_mode(self, value):
        """Set pulse mode (SIN=single, DOU=double, TRI=triple, QUAD=quad)"""
        valid_modes = ['SIN', 'DOU', 'TRI', 'QUAD', 'SINGLE', 'DOUBLE', 'TRIPLE']
        if value.upper() not in valid_modes:
            raise ValueError(f"Mode must be one of {valid_modes}")
        self.instrument.write(f"OUTPUT{self.channel}:PULSE:MODE {value}")

    # Trigger control per channel [6]
    @property
    def retriggerable(self):
        """Get retriggerable delay parameter [6]"""
        return self.instrument.ask(f"{self._prefix}:TRIGGER:RETRIGGERABLE?").strip()

    @retriggerable.setter
    def retriggerable(self, value):
        """Set retriggerable delay parameter [6]"""
        self.instrument.write(f"{self._prefix}:TRIGGER:RETRIGGERABLE {value}")

    @property
    def trigger_prescaler(self):
        """Get trigger prescaler parameter [6]"""
        return int(self.instrument.ask(f"{self._prefix}:TRIGGER:PRESCALER?"))

    @trigger_prescaler.setter
    def trigger_prescaler(self, value):
        """Set trigger prescaler parameter [6]"""
        self.instrument.write(f"{self._prefix}:TRIGGER:PRESCALER {value}")