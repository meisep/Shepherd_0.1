from pymeasure.instruments import Instrument, SCPIMixin
from pymeasure.instruments.validators import strict_discrete_set, strict_range
import numpy as np
import time


# OWON DGE3062 Arbitrary Waveform Generator
# VISA Resource Name: USB0::0x5345::0x1235::25131420::INSTR
# IDN: OWON,DGE3062,25131420,SCPI:99.0 FV:V1.0.3.5.0
#
# Driver written to match the official OWON DGE2000/3000 Series Programmer
# Manual (May 2025 Edition V1.0.1).
#
# Notes specific to this firmware:
#  - Device is not IEEE 488.2 compliant; use write_termination='\n'.
#  - Per the manual, FUNCtion:SHAPe accepts only:
#       SINusoid | SQUare | PULSe | RAMP | PRNoise
#    Arbitrary (ARB) waveforms exist on the instrument but are not selectable
#    via SCPI on this firmware - they must be selected from the front panel
#    after upload.
#  - Arbitrary waveform upload uses a binary block to the EMEMory buffer:
#       DATA:DATA EMEMory,#<n><count><binary_bytes>
#    See OWONAG3062Channel.upload_arbitrary_waveform() for details.


class OWONAG3062(SCPIMixin, Instrument):
    """
    OWON DGE3062 Arbitrary Waveform Generator

    2-channel AWG, 60 MHz bandwidth, 300 MSa/s sample rate.

    Example usage:
        awg = OWONAG3062('USB0::0x5345::0x1235::25131420::INSTR')
        awg.ch1.setup_sine(frequency=1000, amplitude=1.0)
        awg.ch1.output_state = True
        awg.shutdown()
    """

    VISA_ADDRESS = 'USB0::0x5345::0x1235::25131420::INSTR'

    def __init__(self, adapter, name="OWON DGE3062 AWG", **kwargs):
        kwargs.setdefault('write_termination', '\n')
        kwargs.setdefault('read_termination', '\n')
        kwargs.setdefault('timeout', 5000)
        super().__init__(
            adapter,
            name,
            **kwargs
        )
        self.ch1 = OWONAG3062Channel(self, 1)
        self.ch2 = OWONAG3062Channel(self, 2)

    # ---- General system commands ----

    def identify(self):
        """Query instrument identification string (*IDN?)"""
        return self.ask('*IDN?')

    def reset(self):
        """Reset instrument to factory defaults (*RST)"""
        self.write('*RST')
        time.sleep(2)

    def clear_status(self):
        """Clear status registers and error queue (*CLS)"""
        self.write('*CLS')

    def get_error(self):
        """Read the next error from the error queue (SYSTem:ERRor?)"""
        return self.ask('SYSTem:ERRor?')

    def system_version(self):
        """Query the software version (SYSTem:VERSion?)"""
        return self.ask('SYSTem:VERSion?')

    def beep(self):
        """Cause the instrument to beep once (SYSTem:BEEPer)"""
        self.write('SYSTem:BEEPer')

    @property
    def beeper_state(self):
        """Get beeper state (True=ON, False=OFF)"""
        resp = self.ask('SYSTem:BEEPer:STATe?').strip()
        return resp in ('1', 'ON')

    @beeper_state.setter
    def beeper_state(self, value):
        state = 'ON' if value else 'OFF'
        self.write(f'SYSTem:BEEPer:STATe {state}')

    @property
    def display_brightness(self):
        """Get LCD display brightness (0-100)"""
        return int(float(self.ask('DISPlay:BRIGhtness?')))

    @display_brightness.setter
    def display_brightness(self, value):
        if not 0 <= value <= 100:
            raise ValueError('Brightness must be between 0 and 100')
        self.write(f'DISPlay:BRIGhtness {int(value)}')

    # ---- Frequency counter (front-panel counter input) ----

    @property
    def counter_frequency(self):
        return float(self.ask('COUNter:FREQ?'))

    @property
    def counter_period(self):
        return float(self.ask('COUNter:PERiod?'))

    @property
    def counter_duty_cycle(self):
        return float(self.ask('COUNter:DUTYcycle?'))

    @property
    def counter_pulse_width(self):
        return float(self.ask('COUNter:PULSewidth?'))

    @property
    def counter_coupling(self):
        return self.ask('COUNter:COUPling?').strip()

    @counter_coupling.setter
    def counter_coupling(self, value):
        if value.upper() not in ('AC', 'DC'):
            raise ValueError("Coupling must be 'AC' or 'DC'")
        self.write(f'COUNter:COUPling {value.upper()}')

    # ---- Shutdown ----

    def shutdown(self):
        """Safe shutdown - turn off all outputs and close connection"""
        try:
            self.ch1.output_state = False
            self.ch2.output_state = False
        except Exception:
            pass
        finally:
            try:
                if hasattr(self, 'adapter') and self.adapter is not None:
                    self.adapter.connection.close()
                    self.adapter.connection = None
            except Exception:
                pass


class OWONAG3062Channel:
    """
    Represents a single output channel of the OWON DGE3062.

    SCPI prefix: SOURce[1|2] for source commands, OUTPut[1|2] for output state.
    """

    # Per manual page 22: SHAPe accepts only these built-in waveforms.
    WAVEFORMS = ['SINusoid', 'SQUare', 'PULSe', 'RAMP', 'PRNoise',
                 'SIN', 'SQU', 'PUL', 'PRN']

    BURST_MODES = ['TRIGgered', 'GATed', 'TRIG', 'GAT']
    BURST_SOURCES = ['TIMer', 'MANual', 'EXTernal', 'TIM', 'MAN', 'EXT']
    SWEEP_SOURCES = ['TIMer', 'MANual', 'EXTernal', 'TIM', 'MAN', 'EXT']
    SWEEP_SPACINGS = ['LINear', 'LOGarithmic', 'LIN', 'LOG']

    def __init__(self, instrument, channel):
        self.instrument = instrument
        self.channel = channel
        self._prefix = f'SOURce{channel}'

    # ---- Output state and impedance ----

    @property
    def output_state(self):
        """Get output state (True=ON, False=OFF)"""
        resp = self.instrument.ask(f'OUTPut{self.channel}:STATe?').strip()
        return resp in ('1', 'ON')

    @output_state.setter
    def output_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'OUTPut{self.channel}:STATe {state}')
        time.sleep(0.05)

    @property
    def load_impedance(self):
        """Get output load impedance in ohms (or 9.9E+37 for high-Z)"""
        return float(self.instrument.ask(f'OUTPut{self.channel}:IMPedance?'))

    @load_impedance.setter
    def load_impedance(self, value):
        """Set output load impedance (1 to 10000 ohms, or 'INFinity' for high-Z)"""
        if isinstance(value, str):
            self.instrument.write(f'OUTPut{self.channel}:IMPedance {value}')
        else:
            if not 1 <= value <= 10000:
                raise ValueError('Load impedance must be 1 to 10000 ohms, or INFinity')
            self.instrument.write(f'OUTPut{self.channel}:IMPedance {value}')

    # ---- Waveform shape ----

    @property
    def waveform(self):
        """Get waveform shape (SIN, SQU, PUL, RAMP, PRN, or built-in ARB name)"""
        return self.instrument.ask(f'{self._prefix}:FUNCtion:SHAPe?').strip()

    @waveform.setter
    def waveform(self, value):
        """Set waveform shape (SINusoid, SQUare, PULSe, RAMP, PRNoise)"""
        if value.upper() not in [w.upper() for w in self.WAVEFORMS]:
            raise ValueError(f'Waveform must be one of {self.WAVEFORMS}')
        self.instrument.write(f'{self._prefix}:FUNCtion:SHAPe {value}')

    # ---- Frequency / Period ----

    @property
    def frequency(self):
        """Get output frequency in Hz"""
        return float(self.instrument.ask(f'{self._prefix}:FREQuency:FIXed?'))

    @frequency.setter
    def frequency(self, value):
        if not 1e-6 <= value <= 60e6:
            raise ValueError('Frequency must be between 1 uHz and 60 MHz')
        self.instrument.write(f'{self._prefix}:FREQuency:FIXed {value}')

    @property
    def period(self):
        """Get period in seconds"""
        return 1.0 / self.frequency

    @period.setter
    def period(self, value):
        self.frequency = 1.0 / value

    # ---- Voltage: amplitude and offset ----

    @property
    def amplitude(self):
        """Get output amplitude in Vpp"""
        return float(self.instrument.ask(
            f'{self._prefix}:VOLTage:LEVel:IMMediate:AMPLitude?'))

    @amplitude.setter
    def amplitude(self, value):
        if not 0 <= value <= 20:
            raise ValueError('Amplitude must be between 0 and 20 Vpp')
        self.instrument.write(
            f'{self._prefix}:VOLTage:LEVel:IMMediate:AMPLitude {value}')

    @property
    def offset(self):
        """Get DC offset in Volts"""
        return float(self.instrument.ask(
            f'{self._prefix}:VOLTage:LEVel:IMMediate:OFFSet?'))

    @offset.setter
    def offset(self, value):
        self.instrument.write(
            f'{self._prefix}:VOLTage:LEVel:IMMediate:OFFSet {value}')

    # ---- Phase ----

    @property
    def phase(self):
        """Get phase in radians (use phase_degrees for degrees)"""
        return float(self.instrument.ask(f'{self._prefix}:PHASe:ADJust?'))

    @phase.setter
    def phase(self, value):
        if not 0 <= value <= 2 * np.pi:
            raise ValueError('Phase must be between 0 and 2*pi radians')
        self.instrument.write(f'{self._prefix}:PHASe:ADJust {value}')

    @property
    def phase_degrees(self):
        """Get phase in degrees"""
        return np.degrees(self.phase)

    @phase_degrees.setter
    def phase_degrees(self, value):
        if not 0 <= value <= 360:
            raise ValueError('Phase must be between 0 and 360 degrees')
        self.instrument.write(f'{self._prefix}:PHASe:ADJust {value}DEG')

    # ---- Pulse parameters ----

    @property
    def duty_cycle(self):
        """Get pulse waveform duty cycle in percent"""
        return float(self.instrument.ask(f'{self._prefix}:PULSe:DCYCle?'))

    @duty_cycle.setter
    def duty_cycle(self, value):
        self.instrument.write(f'{self._prefix}:PULSe:DCYCle {value}')

    @property
    def pulse_width(self):
        """Get pulse width in seconds"""
        return float(self.instrument.ask(f'{self._prefix}:PULSe:WIDTh?'))

    @pulse_width.setter
    def pulse_width(self, value):
        self.instrument.write(f'{self._prefix}:PULSe:WIDTh {value}')

    @property
    def pulse_rise_time(self):
        """Get pulse leading edge (rise) time in seconds"""
        return float(self.instrument.ask(
            f'{self._prefix}:PULSe:TRANsition:LEADing?'))

    @pulse_rise_time.setter
    def pulse_rise_time(self, value):
        self.instrument.write(
            f'{self._prefix}:PULSe:TRANsition:LEADing {value}')

    @property
    def pulse_fall_time(self):
        """Get pulse trailing edge (fall) time in seconds"""
        return float(self.instrument.ask(
            f'{self._prefix}:PULSe:TRANsition:TRAiling?'))

    @pulse_fall_time.setter
    def pulse_fall_time(self, value):
        self.instrument.write(
            f'{self._prefix}:PULSe:TRANsition:TRAiling {value}')

    # ---- Ramp symmetry ----

    @property
    def ramp_symmetry(self):
        return float(self.instrument.ask(
            f'{self._prefix}:FUNCtion:RAMP:SYMMetry?'))

    @ramp_symmetry.setter
    def ramp_symmetry(self, value):
        if not 0 <= value <= 100:
            raise ValueError('Ramp symmetry must be between 0 and 100 percent')
        self.instrument.write(f'{self._prefix}:FUNCtion:RAMP:SYMMetry {value}')

    # ---- Modulation enable ----
    # Per manual page 23 the keyword is :MODE:STATe (not :MOD:STATe).

    @property
    def modulation_state(self):
        resp = self.instrument.ask(f'{self._prefix}:MODE:STATe?').strip()
        return resp in ('1', 'ON')

    @modulation_state.setter
    def modulation_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:MODE:STATe {state}')

    # ---- AM modulation ----

    @property
    def am_state(self):
        resp = self.instrument.ask(f'{self._prefix}:AM:STATe?').strip()
        return resp in ('1', 'ON')

    @am_state.setter
    def am_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:AM:STATe {state}')

    @property
    def am_depth(self):
        """Get AM modulation depth in percent (0 to 100)"""
        return float(self.instrument.ask(f'{self._prefix}:AM:DEPTh?'))

    @am_depth.setter
    def am_depth(self, value):
        if not 0 <= value <= 100:
            raise ValueError('AM depth must be 0 to 100 percent')
        self.instrument.write(f'{self._prefix}:AM:DEPTh {value}')

    @property
    def am_internal_frequency(self):
        return float(self.instrument.ask(
            f'{self._prefix}:AM:INTernal:FREQuency?'))

    @am_internal_frequency.setter
    def am_internal_frequency(self, value):
        self.instrument.write(f'{self._prefix}:AM:INTernal:FREQuency {value}')

    @property
    def am_internal_function(self):
        return self.instrument.ask(
            f'{self._prefix}:AM:INTernal:FUNCtion?').strip()

    @am_internal_function.setter
    def am_internal_function(self, value):
        self.instrument.write(f'{self._prefix}:AM:INTernal:FUNCtion {value}')

    @property
    def am_source(self):
        return self.instrument.ask(f'{self._prefix}:AM:SOURce?').strip()

    @am_source.setter
    def am_source(self, value):
        self.instrument.write(f'{self._prefix}:AM:SOURce {value}')

    # ---- FM modulation ----

    @property
    def fm_state(self):
        resp = self.instrument.ask(f'{self._prefix}:FM:STATe?').strip()
        return resp in ('1', 'ON')

    @fm_state.setter
    def fm_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:FM:STATe {state}')

    @property
    def fm_deviation(self):
        return float(self.instrument.ask(f'{self._prefix}:FM:DEViation?'))

    @fm_deviation.setter
    def fm_deviation(self, value):
        self.instrument.write(f'{self._prefix}:FM:DEViation {value}')

    @property
    def fm_internal_frequency(self):
        return float(self.instrument.ask(
            f'{self._prefix}:FM:INTernal:FREQuency?'))

    @fm_internal_frequency.setter
    def fm_internal_frequency(self, value):
        self.instrument.write(f'{self._prefix}:FM:INTernal:FREQuency {value}')

    @property
    def fm_internal_function(self):
        return self.instrument.ask(
            f'{self._prefix}:FM:INTernal:FUNCtion?').strip()

    @fm_internal_function.setter
    def fm_internal_function(self, value):
        self.instrument.write(f'{self._prefix}:FM:INTernal:FUNCtion {value}')

    @property
    def fm_source(self):
        return self.instrument.ask(f'{self._prefix}:FM:SOURce?').strip()

    @fm_source.setter
    def fm_source(self, value):
        self.instrument.write(f'{self._prefix}:FM:SOURce {value}')

    # ---- PM modulation ----

    @property
    def pm_state(self):
        resp = self.instrument.ask(f'{self._prefix}:PM:STATe?').strip()
        return resp in ('1', 'ON')

    @pm_state.setter
    def pm_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:PM:STATe {state}')

    @property
    def pm_deviation(self):
        """Get PM phase deviation in radians"""
        return float(self.instrument.ask(f'{self._prefix}:PM:DEViation?'))

    @pm_deviation.setter
    def pm_deviation(self, value):
        self.instrument.write(f'{self._prefix}:PM:DEViation {value}')

    @property
    def pm_internal_frequency(self):
        return float(self.instrument.ask(
            f'{self._prefix}:PM:INTernal:FREQuency?'))

    @pm_internal_frequency.setter
    def pm_internal_frequency(self, value):
        self.instrument.write(f'{self._prefix}:PM:INTernal:FREQuency {value}')

    @property
    def pm_internal_function(self):
        return self.instrument.ask(
            f'{self._prefix}:PM:INTernal:FUNCtion?').strip()

    @pm_internal_function.setter
    def pm_internal_function(self, value):
        self.instrument.write(f'{self._prefix}:PM:INTernal:FUNCtion {value}')

    @property
    def pm_source(self):
        return self.instrument.ask(f'{self._prefix}:PM:SOURce?').strip()

    @pm_source.setter
    def pm_source(self, value):
        self.instrument.write(f'{self._prefix}:PM:SOURce {value}')

    # ---- Burst mode ----

    @property
    def burst_state(self):
        """Get burst mode state (True=ON, False=OFF)"""
        resp = self.instrument.ask(f'{self._prefix}:BURSt:STATe?').strip()
        return resp in ('1', 'ON')

    @burst_state.setter
    def burst_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:BURSt:STATe {state}')

    @property
    def burst_mode(self):
        """Get burst mode ('TRIG' or 'GAT')"""
        return self.instrument.ask(f'{self._prefix}:BURSt:MODE?').strip()

    @burst_mode.setter
    def burst_mode(self, value):
        if value.upper() not in [m.upper() for m in self.BURST_MODES]:
            raise ValueError(f'Burst mode must be one of {self.BURST_MODES}')
        self.instrument.write(f'{self._prefix}:BURSt:MODE {value}')

    @property
    def burst_ncycles(self):
        return int(float(self.instrument.ask(f'{self._prefix}:BURSt:NCYCles?')))

    @burst_ncycles.setter
    def burst_ncycles(self, value):
        """Set burst cycle count (1 to 500000)"""
        self.instrument.write(f'{self._prefix}:BURSt:NCYCles {int(value)}')

    @property
    def burst_source(self):
        """Get burst trigger source ('TIM', 'MAN', or 'EXT')"""
        return self.instrument.ask(f'{self._prefix}:BURSt:SOURce?').strip()

    @burst_source.setter
    def burst_source(self, value):
        """Set burst trigger source ('TIMer', 'MANual', or 'EXTernal')"""
        if value.upper() not in [s.upper() for s in self.BURST_SOURCES]:
            raise ValueError(f'Burst source must be one of {self.BURST_SOURCES}')
        self.instrument.write(f'{self._prefix}:BURSt:SOURce {value}')

    @property
    def burst_internal_period(self):
        """Get internal burst period in seconds"""
        return float(self.instrument.ask(
            f'{self._prefix}:BURSt:INTernal:PERiod?'))

    @burst_internal_period.setter
    def burst_internal_period(self, value):
        self.instrument.write(f'{self._prefix}:BURSt:INTernal:PERiod {value}')

    @property
    def burst_gate_polarity(self):
        return self.instrument.ask(
            f'{self._prefix}:BURSt:GATE:POLarity?').strip()

    @burst_gate_polarity.setter
    def burst_gate_polarity(self, value):
        self.instrument.write(f'{self._prefix}:BURSt:GATE:POLarity {value}')

    # ---- Frequency sweep ----

    @property
    def sweep_state(self):
        resp = self.instrument.ask(f'{self._prefix}:SWEep:STATe?').strip()
        return resp in ('1', 'ON')

    @sweep_state.setter
    def sweep_state(self, value):
        state = 'ON' if value else 'OFF'
        self.instrument.write(f'{self._prefix}:SWEep:STATe {state}')

    @property
    def sweep_time(self):
        """Get sweep time in seconds (1 ms to 500 s)"""
        return float(self.instrument.ask(f'{self._prefix}:SWEep:TIME?'))

    @sweep_time.setter
    def sweep_time(self, value):
        if not 1e-3 <= value <= 500:
            raise ValueError('Sweep time must be between 1 ms and 500 s')
        self.instrument.write(f'{self._prefix}:SWEep:TIME {value}')

    @property
    def sweep_source(self):
        return self.instrument.ask(f'{self._prefix}:SWEep:SOURce?').strip()

    @sweep_source.setter
    def sweep_source(self, value):
        if value.upper() not in [s.upper() for s in self.SWEEP_SOURCES]:
            raise ValueError(f'Sweep source must be one of {self.SWEEP_SOURCES}')
        self.instrument.write(f'{self._prefix}:SWEep:SOURce {value}')

    @property
    def sweep_spacing(self):
        return self.instrument.ask(f'{self._prefix}:SWEep:SPACing?').strip()

    @sweep_spacing.setter
    def sweep_spacing(self, value):
        if value.upper() not in [s.upper() for s in self.SWEEP_SPACINGS]:
            raise ValueError(f'Sweep spacing must be one of {self.SWEEP_SPACINGS}')
        self.instrument.write(f'{self._prefix}:SWEep:SPACing {value}')

    @property
    def sweep_start_freq(self):
        return float(self.instrument.ask(f'{self._prefix}:FREQuency:STARt?'))

    @sweep_start_freq.setter
    def sweep_start_freq(self, value):
        self.instrument.write(f'{self._prefix}:FREQuency:STARt {value}')

    @property
    def sweep_stop_freq(self):
        return float(self.instrument.ask(f'{self._prefix}:FREQuency:STOP?'))

    @sweep_stop_freq.setter
    def sweep_stop_freq(self, value):
        self.instrument.write(f'{self._prefix}:FREQuency:STOP {value}')

    @property
    def sweep_center_freq(self):
        return float(self.instrument.ask(f'{self._prefix}:FREQuency:CENTer?'))

    @sweep_center_freq.setter
    def sweep_center_freq(self, value):
        self.instrument.write(f'{self._prefix}:FREQuency:CENTer {value}')

    @property
    def sweep_span(self):
        return float(self.instrument.ask(f'{self._prefix}:FREQuency:SPAN?'))

    @sweep_span.setter
    def sweep_span(self, value):
        self.instrument.write(f'{self._prefix}:FREQuency:SPAN {value}')

    # ---- Arbitrary waveform upload via TRACe|DATA[:DATA] EMEMory ----

    def upload_arbitrary_waveform(self, data):
        """
        Upload arbitrary waveform data to the EMEMory edit buffer.

        Per the manual (page 34), the upload command is:
            DATA:DATA EMEMory,<binary_block_data>

        The binary block format is: #<n><count><bytes>
            <n>     = number of digits in <count>
            <count> = number of bytes that follow
            <bytes> = raw waveform samples, 2 bytes each (uint16, little-endian)

        IMPORTANT: This SCPI command transfers the data successfully (verified
        with readback), but on this firmware the instrument does not provide a
        SCPI command to play back the EMEMory buffer. After upload, the user
        must select the corresponding ARB entry from the front panel manually.

        Args:
            data: Array-like of values. If values are in [-1, 1] they are
                  treated as normalized and scaled to the 14-bit DAC range
                  [0, 16383]. Otherwise, values are clipped to [0, 16383].
        """
        data = np.asarray(data, dtype=float)

        if data.min() >= -1.0 and data.max() <= 1.0:
            dac_values = ((data + 1.0) / 2.0 * 16383).astype(np.uint16)
        else:
            dac_values = np.clip(data, 0, 16383).astype(np.uint16)

        binary_data = dac_values.tobytes()
        byte_count = len(binary_data)
        count_str = str(byte_count)
        header = f'#{len(count_str)}{count_str}'

        cmd_prefix = b'DATA:DATA EMEMory,' + header.encode('ascii')
        terminator = b'\n'
        self.instrument.adapter.connection.write_raw(
            cmd_prefix + binary_data + terminator
        )
        time.sleep(1.0)

    def query_arbitrary_waveform(self):
        """
        Read back the waveform currently stored in the EMEMory edit buffer.

        Returns the raw binary block bytes (header + data). Useful for
        verifying that an upload landed correctly.
        """
        self.instrument.write('DATA:DATA? EMEMory')
        return self.instrument.adapter.connection.read_raw()

    # ---- Convenience setup methods ----

    def setup_sine(self, frequency, amplitude, offset=0.0, phase_deg=0.0):
        """Configure channel as a sine wave."""
        self.waveform = 'SINusoid'
        self.frequency = frequency
        self.amplitude = amplitude
        self.offset = offset
        if phase_deg != 0.0:
            self.phase_degrees = phase_deg

    def setup_square(self, frequency, amplitude, offset=0.0, duty_cycle=50.0):
        """Configure channel as a square wave with the given duty cycle."""
        self.waveform = 'SQUare'
        self.frequency = frequency
        self.amplitude = amplitude
        self.offset = offset
        self.duty_cycle = duty_cycle

    def setup_pulse(self, frequency, amplitude, width, offset=0.0):
        """Configure channel as a pulse with the given width."""
        self.waveform = 'PULSe'
        self.frequency = frequency
        self.amplitude = amplitude
        self.offset = offset
        self.pulse_width = width

    def setup_ramp(self, frequency, amplitude, offset=0.0, symmetry=50.0):
        """Configure channel as a ramp wave with the given symmetry."""
        self.waveform = 'RAMP'
        self.frequency = frequency
        self.amplitude = amplitude
        self.offset = offset
        self.ramp_symmetry = symmetry

    def setup_noise(self, amplitude, offset=0.0):
        """Configure channel as pseudo-random noise."""
        self.waveform = 'PRNoise'
        self.amplitude = amplitude
        self.offset = offset

    def setup_burst(self, ncycles=1, mode='TRIGgered', source='MANual'):
        """
        Convenience method: configure burst mode.

        After calling this, send `awg.write('*TRG')` to fire a burst when
        source='MANual'.
        """
        self.burst_mode = mode
        self.burst_ncycles = ncycles
        self.burst_source = source
        self.burst_state = True
        