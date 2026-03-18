"""
Multi-Pulse Burst Measurement GUI using PyMeasure
"""
import sys
import time
import numpy as np
from pymeasure.display.Qt import QtWidgets
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import IntegerParameter, FloatParameter, ListParameter, Parameter

from bnc765_driver import BNC765
from tds6604_driver import TDS6604


class MultiPulseProcedure(Procedure):
    """
    Procedure for multi-pulse burst measurement
    """

    # Instrument addresses
    pulser_address = Parameter('Pulser Address', default='TCPIP::169.254.125.69::INSTR')
    scope_address = Parameter('Scope Address', default='GPIB0::2::INSTR')

    # Channel 1 Configuration
    ch1_enabled = ListParameter('CH1 Enabled', choices=['Yes', 'No'], default='Yes')
    ch1_num_pulses = IntegerParameter('CH1 Number of Pulses', minimum=1, maximum=4, default=2)
    ch1_voltage = FloatParameter('CH1 Voltage', units='V', minimum=0.1, maximum=3.0, default=0.2)
    ch1_inverted = ListParameter('CH1 Polarity', choices=['Normal', 'Inverted'], default='Normal')

    # Channel 1 Pulse Parameters (up to 4 pulses)
    ch1_p1_width = FloatParameter('CH1 P1 Width', units='ns', minimum=0.1, maximum=20, default=0.5)
    ch1_p1_delay = FloatParameter('CH1 P1 Delay', units='ns', minimum=0, maximum=100, default=5.0)

    ch1_p2_width = FloatParameter('CH1 P2 Width', units='ns', minimum=0.1, maximum=20, default=0.5)
    ch1_p2_delay = FloatParameter('CH1 P2 Delay', units='ns', minimum=0, maximum=100, default=8.0)

    ch1_p3_width = FloatParameter('CH1 P3 Width', units='ns', minimum=0.1, maximum=20, default=1.0)
    ch1_p3_delay = FloatParameter('CH1 P3 Delay', units='ns', minimum=0, maximum=100, default=0.0)

    ch1_p4_width = FloatParameter('CH1 P4 Width', units='ns', minimum=0.1, maximum=20, default=1.0)
    ch1_p4_delay = FloatParameter('CH1 P4 Delay', units='ns', minimum=0, maximum=100, default=0.0)

    # Channel 2 Configuration
    ch2_enabled = ListParameter('CH2 Enabled', choices=['Yes', 'No'], default='Yes')
    ch2_num_pulses = IntegerParameter('CH2 Number of Pulses', minimum=1, maximum=4, default=1)
    ch2_voltage = FloatParameter('CH2 Voltage', units='V', minimum=0.1, maximum=2.0, default=0.2)
    ch2_inverted = ListParameter('CH2 Polarity', choices=['Normal', 'Inverted'], default='Inverted')

    # Channel 2 Pulse Parameters
    ch2_p1_width = FloatParameter('CH2 P1 Width', units='ns', minimum=0.1, maximum=20, default=0.5)
    ch2_p1_delay = FloatParameter('CH2 P1 Delay', units='ns', minimum=0, maximum=100, default=1.0)

    ch2_p2_width = FloatParameter('CH2 P2 Width', units='ns', minimum=0.1, maximum=20, default=1.0)
    ch2_p2_delay = FloatParameter('CH2 P2 Delay', units='ns', minimum=0, maximum=100, default=0.0)

    ch2_p3_width = FloatParameter('CH2 P3 Width', units='ns', minimum=0.1, maximum=20, default=1.0)
    ch2_p3_delay = FloatParameter('CH2 P3 Delay', units='ns', minimum=0, maximum=100, default=0.0)

    ch2_p4_width = FloatParameter('CH2 P4 Width', units='ns', minimum=0.1, maximum=20, default=1.0)
    ch2_p4_delay = FloatParameter('CH2 P4 Delay', units='ns', minimum=0, maximum=100, default=0.0)

    # Scope Configuration
    capture_width = FloatParameter('Capture Width', units='µs', minimum=0.01, maximum=1000, default=10.0)
    trigger_delay = FloatParameter('Trigger Delay', units='ns', minimum=0, maximum=20, default=5.0)
    record_length = IntegerParameter('Record Length', minimum=1000, maximum=100000, default=10000)
    trigger_channel = IntegerParameter('Trigger Channel', minimum=1, maximum=4, default=4)
    signal_channel = IntegerParameter('Signal Channel', minimum=1, maximum=4, default=1)

    # Data columns
    DATA_COLUMNS = ['Time (s)', 'CH1 Voltage (V)', 'CH4 Voltage (V)']

    def startup(self):
        """Initialize instruments"""
        self.emit('status', 'Connecting to instruments...')

        # Connect to pulser
        self.pulser = BNC765(self.pulser_address)
        self.emit('status', f'Connected to pulser: {self.pulser.id}')

        # Connect to scope
        self.scope = TDS6604(self.scope_address)
        self.emit('status', f'Connected to scope: {self.scope.id}')

    def execute(self):
        """Execute the measurement"""

        # Setup Channel 1 if enabled
        if self.ch1_enabled == 'Yes':
            self.emit('status', 'Configuring Pulser Channel 1...')
            self._setup_channel(
                channel=1,
                num_pulses=self.ch1_num_pulses,
                voltage=self.ch1_voltage,
                inverted=(self.ch1_inverted == 'Inverted'),
                pulse_params=[
                    {'width_ns': self.ch1_p1_width, 'delay_ns': self.ch1_p1_delay},
                    {'width_ns': self.ch1_p2_width, 'delay_ns': self.ch1_p2_delay},
                    {'width_ns': self.ch1_p3_width, 'delay_ns': self.ch1_p3_delay},
                    {'width_ns': self.ch1_p4_width, 'delay_ns': self.ch1_p4_delay},
                ][:self.ch1_num_pulses]
            )

        # Setup Channel 2 if enabled
        if self.ch2_enabled == 'Yes':
            self.emit('status', 'Configuring Pulser Channel 2...')
            self._setup_channel(
                channel=2,
                num_pulses=self.ch2_num_pulses,
                voltage=self.ch2_voltage,
                inverted=(self.ch2_inverted == 'Inverted'),
                pulse_params=[
                    {'width_ns': self.ch2_p1_width, 'delay_ns': self.ch2_p1_delay},
                    {'width_ns': self.ch2_p2_width, 'delay_ns': self.ch2_p2_delay},
                    {'width_ns': self.ch2_p3_width, 'delay_ns': self.ch2_p3_delay},
                    {'width_ns': self.ch2_p4_width, 'delay_ns': self.ch2_p4_delay},
                ][:self.ch2_num_pulses]
            )

        # Setup scope
        self.emit('status', 'Configuring oscilloscope...')
        self._setup_scope()

        # Arm scope
        self.emit('status', 'Arming oscilloscope...')
        self.scope.arm()
        time.sleep(0.3)

        # Trigger pulser
        self.emit('status', 'Triggering pulse burst...')
        self.pulser.trigger()

        # Wait for trigger
        self.emit('status', 'Waiting for scope trigger...')
        if not self.scope.wait_for_trigger(timeout=5):
            raise Exception("Scope did not trigger!")

        self.emit('status', 'Acquiring waveforms...')

        # Get waveforms
        ch1_data = self.scope.ch1.get_waveform()
        ch4_data = self.scope.ch4.get_waveform()

        self.emit('status', f'Retrieved {len(ch1_data["voltage"])} points')

        # Emit data points
        for i in range(len(ch1_data['time'])):
            data = {
                'Time (s)': ch1_data['time'][i],
                'CH1 Voltage (V)': ch1_data['voltage'][i],
                'CH4 Voltage (V)': ch4_data['voltage'][i]
            }
            self.emit('results', data)

            if self.should_stop():
                break

        self.emit('status', 'Measurement complete!')

    def _setup_channel(self, channel, num_pulses, voltage, inverted, pulse_params):
        """Setup a single pulser channel with multi-pulse configuration"""

        pulse_mode_map = {1: 'SIN', 2: 'DOU', 3: 'TRI', 4: 'QUAD'}
        pulse_mode = pulse_mode_map[num_pulses]

        ch = getattr(self.pulser, f'ch{channel}')

        # Stop and configure
        self.pulser.stop()
        ch.output_state = False
        time.sleep(0.3)

        # Set pulse mode
        ch.pulse_mode = pulse_mode
        time.sleep(0.2)

        # Set shared parameters
        ch.voltage_level = voltage
        ch.inverted = inverted
        ch.load_impedance = 50

        # Configure individual pulses
        for i, pulse in enumerate(pulse_params):
            pulse_num = i + 1
            pulse_prefix = f'SOURCE{channel}:PULSE{pulse_num}'
            self.pulser.write(f'{pulse_prefix}:WIDTH {pulse["width_ns"]}E-9')
            self.pulser.write(f'{pulse_prefix}:DELAY {pulse["delay_ns"]}E-9')

        # Set frequency and burst
        freq_hz = 1 / (self.capture_width * 1e-6)  # capture_width is in µs
        ch.frequency = freq_hz
        ch.burst_ncycles = 1

        # Set trigger mode
        self.pulser.trigger_mode = 'BURST'
        self.pulser.trigger_source = 'MANUAL'

        # Trigger output
        self.pulser.trigger_output_amplitude = 0.9
        self.pulser.trigger_output_polarity = 'POSITIVE'
        self.pulser.write(f'TRIGGER:OUTPUT:SOURCE OUT{channel}')

        # Enable and start
        ch.output_state = True
        self.pulser.start()

    def _setup_scope(self):
        """Setup oscilloscope for acquisition"""

        # Signal channel
        sig_ch = getattr(self.scope, f'ch{self.signal_channel}')
        sig_ch.enabled = True
        sig_ch.coupling = 'DC'
        sig_ch.impedance = 'FIFTY'

        # Use max voltage from enabled channels
        max_voltage = 0
        if self.ch1_enabled == 'Yes':
            max_voltage = max(max_voltage, self.ch1_voltage)
        if self.ch2_enabled == 'Yes':
            max_voltage = max(max_voltage, self.ch2_voltage)

        sig_ch.scale = max_voltage / 4
        sig_ch.position = -2

        # Trigger channel
        trig_ch = getattr(self.scope, f'ch{self.trigger_channel}')
        trig_ch.enabled = True
        trig_ch.coupling = 'DC'
        trig_ch.impedance = 'FIFTY'
        trig_ch.scale = 0.25
        trig_ch.position = 2

        # Record length
        self.scope.record_length = self.record_length

        # Timebase
        total_time_s = (self.trigger_delay * 1e-9) + (self.capture_width * 1e-6)
        self.scope.timebase = total_time_s / 10

        # Trigger
        self.scope.setup_edge_trigger(
            source=f'CH{self.trigger_channel}',
            level=0.45,
            slope='RISE',
            mode='NORMAL'
        )
        self.scope.horizontal_position = 20

        # Acquisition
        self.scope.acquisition_mode = 'SAMPLE'
        self.scope.acquisition_stopafter = 'SEQUENCE'

    def shutdown(self):
        """Cleanup after measurement"""

        self.emit('status', 'Cleaning up...')

        try:
            # Stop pulser channels
            if hasattr(self, 'pulser'):
                if self.ch1_enabled == 'Yes':
                    self.pulser.ch1.output_state = False
                if self.ch2_enabled == 'Yes':
                    self.pulser.ch2.output_state = False
                self.pulser.stop()
                self.pulser.shutdown()
        except:
            pass

        try:
            if hasattr(self, 'scope'):
                self.scope.shutdown()
        except:
            pass

        self.emit('status', 'Shutdown complete')


class MultiPulseWindow(ManagedWindow):
    """
    Main window for multi-pulse measurement
    """

    def __init__(self):
        super().__init__(
            procedure_class=MultiPulseProcedure,
            inputs=[
                'pulser_address',
                'scope_address',
                'ch1_enabled',
                'ch1_num_pulses',
                'ch1_voltage',
                'ch1_inverted',
                'ch1_p1_width',
                'ch1_p1_delay',
                'ch1_p2_width',
                'ch1_p2_delay',
                'ch1_p3_width',
                'ch1_p3_delay',
                'ch1_p4_width',
                'ch1_p4_delay',
                'ch2_enabled',
                'ch2_num_pulses',
                'ch2_voltage',
                'ch2_inverted',
                'ch2_p1_width',
                'ch2_p1_delay',
                # 'ch2_p2_width',
                # 'ch2_p2_delay',
                # 'ch2_p3_width',
                # 'ch2_p3_delay',
                # 'ch2_p4_width',
                # 'ch2_p4_delay',
                'capture_width',
                'trigger_delay',
                'record_length',
                'trigger_channel',
                'signal_channel',
            ],
            displays=[
                'pulser_address',
                'scope_address',
            ],
            x_axis='Time (s)',
            y_axis='CH1 Voltage (V)',
            # directory_input=True,
        )
        self.setWindowTitle('Multi-Pulse Burst Measurement')

        # Add scrollbar to inputs
        from pymeasure.display.Qt import QtWidgets
        QtWidgets.QApplication.processEvents()  # Let GUI build first

        for dock in self.findChildren(QtWidgets.QDockWidget):
            widget = dock.widget()
            if widget and hasattr(widget, 'layout'):
                scroll = QtWidgets.QScrollArea()
                scroll.setWidget(widget)
                scroll.setWidgetResizable(True)
                scroll.setMinimumWidth(350)
                dock.setWidget(scroll)

    def queue(self):
        """Queue a measurement"""

        # Create filename based on configuration
        filename_parts = []

        procedure = self.make_procedure()

        if procedure.ch1_enabled == 'Yes':
            filename_parts.append(f'CH1_{procedure.ch1_num_pulses}p')
        if procedure.ch2_enabled == 'Yes':
            filename_parts.append(f'CH2_{procedure.ch2_num_pulses}p')

        filename = '_'.join(filename_parts) + '.csv'

        # Queue the measurement
        results = Results(procedure, filename)
        experiment = self.new_experiment(results)

        self.manager.queue(experiment)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MultiPulseWindow()
    window.show()
    sys.exit(app.exec())