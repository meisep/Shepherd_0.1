from pymeasure.instruments import Instrument, SCPIMixin
from pymeasure.instruments.validators import strict_discrete_set, strict_range
import numpy as np
import time


class TDS6604(SCPIMixin, Instrument):
    """
    Tektronix TDS6604 Oscilloscope
    """

    def __init__(self, adapter, name="TDS6604 Oscilloscope", **kwargs):
        super().__init__(
            adapter,
            name,
            # includeSCPI=True,
            **kwargs
        )

        # Create channel objects
        self.ch1 = TDS6604Channel(self, 1)
        self.ch2 = TDS6604Channel(self, 2)
        self.ch3 = TDS6604Channel(self, 3)
        self.ch4 = TDS6604Channel(self, 4)

    # Timebase
    timebase = Instrument.control(
        "HORIZONTAL:MAIN:SCALE?", "HORIZONTAL:MAIN:SCALE %g",
        """Horizontal scale in seconds/division"""
    )

    record_length = Instrument.control(
        "HORIZONTAL:RECORDLENGTH?", "HORIZONTAL:RECORDLENGTH %d",
        """Record length (number of points)""",
        cast=int,
        get_process=lambda v: int(float(v))
    )

    horizontal_position = Instrument.control(
        "HORIZONTAL:MAIN:POSITION?", "HORIZONTAL:MAIN:POSITION %g",
        """Horizontal trigger position in percent"""
    )

    # Trigger
    trigger_source = Instrument.control(
        "TRIGGER:A:EDGE:SOURCE?", "TRIGGER:A:EDGE:SOURCE %s",
        """Trigger source (CH1, CH2, CH3, CH4, EXT, LINE)"""
    )

    trigger_slope = Instrument.control(
        "TRIGGER:A:EDGE:SLOPE?", "TRIGGER:A:EDGE:SLOPE %s",
        """Trigger slope (RISE, FALL)""",
        validator=strict_discrete_set,
        values=['RISE', 'FALL']
    )

    trigger_mode = Instrument.control(
        "TRIGGER:A:MODE?", "TRIGGER:A:MODE %s",
        """Trigger mode (AUTO, NORMAL)""",
        validator=strict_discrete_set,
        values=['AUTO', 'NORMAL']
    )

    trigger_type = Instrument.control(
        "TRIGGER:A:TYPE?", "TRIGGER:A:TYPE %s",
        """Trigger type (EDGE, LOGIC, PULSE, etc.)"""
    )

    trigger_state = Instrument.measurement(
        "TRIGGER:STATE?",
        """Query the trigger state"""
    )

    # Acquisition
    acquisition_mode = Instrument.control(
        "ACQUIRE:MODE?", "ACQUIRE:MODE %s",
        """Acquisition mode (SAMPLE, AVERAGE, PEAKDETECT, ENVELOPE)""",
        validator=strict_discrete_set,
        values=['SAMPLE', 'AVERAGE', 'PEAKDETECT', 'ENVELOPE', 'SAMP', 'AVE', 'PEAK', 'ENV']
    )

    acquisition_stopafter = Instrument.control(
        "ACQUIRE:STOPAFTER?", "ACQUIRE:STOPAFTER %s",
        """Stop after mode (RUNSTOP, SEQUENCE)""",
        validator=strict_discrete_set,
        values=['RUNSTOP', 'SEQUENCE', 'RUNS', 'SEQ']
    )

    acquisition_numavg = Instrument.control(
        "ACQUIRE:NUMAVG?", "ACQUIRE:NUMAVG %d",
        """Number of waveforms to average (1-10000)"""
    )

    acquisition_numavg_current = Instrument.measurement(
        "ACQUIRE:NUMACQ?",  # Query current number of acquisitions completed
        """Get the current number of acquisitions completed in average mode"""
    )

    @property
    def acquisition_state(self):
        """Get acquisition state (True=running, False=stopped)"""
        return bool(int(self.ask("ACQUIRE:STATE?")))

    @acquisition_state.setter
    def acquisition_state(self, value):
        """Set acquisition state (True=run, False=stop)"""
        state = "RUN" if value else "STOP"
        self.write(f"ACQUIRE:STATE {state}")

    def set_trigger_level(self, level):
        """
        Set trigger level for specific channel

        Args:
            channel: Channel number (1-4)
            level: Trigger level in volts
        """
        self.write(f"TRIGGER:A:LEVEL {level}")

    def get_trigger_level(self, channel):
        """
        Get trigger level for specific channel

        Args:
            channel: Channel number (1-4)

        Returns:
            float: Trigger level in volts
        """
        return float(self.ask(f"TRIGGER:A:LEVEL?"))

    def arm(self):
        """Arm scope for single acquisition"""
        self.acquisition_stopafter = 'SEQUENCE'
        self.acquisition_state = True
        time.sleep(0.3)

    def run(self):
        """Set scope to continuous run mode"""
        self.acquisition_stopafter = 'RUNSTOP'
        self.acquisition_state = True

    def stop(self):
        """Stop acquisition"""
        self.acquisition_state = False

    def wait_for_trigger(self, timeout=5):
        """
        Wait for scope to trigger and complete acquisition

        Args:
            timeout: Timeout in seconds

        Returns:
            bool: True if triggered, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            if not self.acquisition_state:  # Stopped = triggered
                return True
            time.sleep(0.05)
        return False


    def force_trigger(self):
        """Force a trigger"""
        self.write("TRIGGER FORCE")

    horizontal_position = Instrument.control(
        "HORIZONTAL:MAIN:POSITION?", "HORIZONTAL:MAIN:POSITION %g",
        """Horizontal trigger position in percent"""
    )

    horizontal_delay_time = Instrument.control(
        "HORIZONTAL:DELAY:TIME?", "HORIZONTAL:DELAY:TIME %g",
        """Horizontal delay time in seconds"""
    )

    horizontal_delay_mode = Instrument.control(
        "HORIZONTAL:DELAY:MODE?", "HORIZONTAL:DELAY:MODE %d",
        """Horizontal delay mode (0=off, 1=on)""",
        cast=int,
        get_process=lambda v: int(float(v))
    )


#######################

    def setup_edge_trigger(self, source, level, slope='RISE', mode='NORMAL', delay=0):
        """
        Setup edge trigger

        Args:
            source: Trigger source (e.g., 'CH1', 'CH4', 'EXT')
            level: Trigger level in volts
            slope: Trigger slope ('RISE' or 'FALL')
            mode: Trigger mode ('NORMAL' or 'AUTO')
        """
        self.horizontal_delay_mode = delay
        self.horizontal_position=10
        self.trigger_type = 'EDGE'
        self.trigger_source = source
        self.trigger_slope = slope
        self.trigger_mode = mode

        # Set level based on source type
        if source.startswith('CH'):
            channel = int(source[2])
            self.set_trigger_level(level)
        else:
            self.write(f"TRIGGER:A:LEVEL {level}")


    def __del__(self):
        """Destructor to prevent double-close errors"""
        try:
            if hasattr(self, 'adapter') and self.adapter:
                # Don't call shutdown, just close adapter
                pass
        except:
            pass


class TDS6604Channel:
    """
    Represents a single channel of the TDS6604
    """

    def __init__(self, instrument, channel):
        self.instrument = instrument
        self.channel = channel
        self._prefix = f"CH{channel}"
        self._scale_cache = None

    # Channel state
    @property
    def enabled(self):
        """Get channel enabled state"""
        return bool(int(self.instrument.ask(f"SELECT:{self._prefix}?")))

    @enabled.setter
    def enabled(self, value):
        """Set channel enabled state"""
        state = "ON" if value else "OFF"
        self.instrument.write(f"SELECT:{self._prefix} {state}")

    # Vertical
    @property
    def scale(self):
        """Get vertical scale in V/division"""
        return float(self.instrument.ask(f"{self._prefix}:SCALE?"))

    @scale.setter
    def scale(self, value):
        """Set vertical scale in V/division"""
        self.instrument.write(f"{self._prefix}:SCALE {value}")

    @property
    def position(self):
        """Get vertical position in divisions"""
        return float(self.instrument.ask(f"{self._prefix}:POSITION?"))

    @position.setter
    def position(self, value):
        """Set vertical position in divisions"""
        self.instrument.write(f"{self._prefix}:POSITION {value}")

    @property
    def coupling(self):
        """Get coupling (DC, AC, GND)"""
        return self.instrument.ask(f"{self._prefix}:COUPLING?").strip()

    @coupling.setter
    def coupling(self, value):
        """Set coupling (DC, AC, GND)"""
        self.instrument.write(f"{self._prefix}:COUPLING {value}")

    @property
    def impedance(self):
        """Get input impedance (FIFTY, ONEMEG)"""
        return self.instrument.ask(f"{self._prefix}:IMPEDANCE?").strip()

    @impedance.setter
    def impedance(self, value):
        """Set input impedance (FIFTY, ONEMEG)"""
        self.instrument.write(f"{self._prefix}:IMPEDANCE {value}")

    @property
    def bandwidth(self):
        """Get bandwidth limit setting"""
        return self.instrument.ask(f"{self._prefix}:BANDWIDTH?").strip()

    @bandwidth.setter
    def bandwidth(self, value):
        """Set bandwidth limit (FULL, 20, 200, etc.)"""
        self.instrument.write(f"{self._prefix}:BANDWIDTH {value}")


    def get_waveform(self):
        """
        Get waveform data - FAST VERSION using direct VISA

        Returns:
            dict: {'time': np.array, 'voltage': np.array, 'channel': int}
        """
        # Get the underlying VISA resource
        visa_resource = self.instrument.adapter.connection

        # Setup data source and encoding - send as single command
        record_length = self.instrument.record_length

        setup_cmd = (f'DATA:SOURCE {self._prefix};'
                     f'ENCDG RIBINARY;'
                     f'WIDTH 2;'
                     f'START 1;'
                     f'STOP {record_length}')
        visa_resource.write(setup_cmd)

        # Get scaling parameters - cache them
        if not hasattr(self, '_scale_cache') or self._scale_cache is None:
            # Query all at once if possible, or individually
            self._scale_cache = {
                'x_incr': float(visa_resource.query('WFMPRE:XINCR?')),
                'x_zero': float(visa_resource.query('WFMPRE:XZERO?')),
                'y_mult': float(visa_resource.query('WFMPRE:YMULT?')),
                'y_zero': float(visa_resource.query('WFMPRE:YZERO?')),
                'y_off': float(visa_resource.query('WFMPRE:YOFF?'))
            }

        sc = self._scale_cache

        # Get curve data - direct VISA read
        visa_resource.write('CURVE?')
        raw_data = visa_resource.read_raw()

        # Parse binary header: #<x><yyy><data>
        header_len = 2 + int(chr(raw_data[1]))
        byte_count = int(raw_data[2:header_len].decode('ascii'))
        data_bytes = raw_data[header_len:header_len + byte_count]

        # Convert to voltage
        voltage_raw = np.frombuffer(data_bytes, dtype=np.dtype('>i2'))
        voltage = (voltage_raw - sc['y_off']) * sc['y_mult'] + sc['y_zero']

        # Time array
        time_array = np.arange(len(voltage)) * sc['x_incr'] + sc['x_zero']

        return {
            'time': time_array,
            'voltage': voltage,
            'channel': self.channel
        }

    def refresh_scaling(self):
        """Call this after changing vertical scale or timebase"""
        self._scale_cache = None