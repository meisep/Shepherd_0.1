import sys
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import FloatParameter, IntegerParameter, Parameter
import logging
from pulse_3pp import run_3pp, connect_instruments
from pymeasure.display.Qt import QtWidgets
from pathlib import Path

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class ThreePulseProcedure(Procedure):
    """Procedure for 3PP measurements"""
    # Pulse parameters
    u_amplitude = FloatParameter('U Amplitude', units='V', default=0.5)
    u_to_n_delay = FloatParameter('U to N Delay', units='ns', default=500.0)
    nd_amplitude = FloatParameter('N/D Amplitude', units='V', default=0.5)
    n_to_d_delay = FloatParameter('N to D Delay', units='ns', default=100.0)
    polarity = Parameter('Polarity', default='npp')
    # Voltage parameters
    base_offset = FloatParameter('Base Offset', units='V', default=0)
    pulse_width_ns = FloatParameter('Pulse Width', units='ns', default=200.0)
    # Scope parameters
    capture_width_ns = FloatParameter('Capture Width', units='ns', default=2000.0)
    record_length = IntegerParameter('Record Length', default=10000)
    vdiv = FloatParameter('V/div', units='V', default=0.2)
    num_averages = IntegerParameter('num Averages', default=4)
    # Saving parameters
    save_directory = Parameter('Save Directory', default='test_3pp')

    # Enable sequencer for these parameters
    SEQUENCER_INPUTS = ['u_amplitude', 'nd_amplitude', 'u_to_n_delay', 'n_to_d_delay']
    DATA_COLUMNS = ['time_ns', 'voltage_V']

    # Class-level instrument storage
    _scope = None
    _pulser = None

    def startup(self):
        """Called once before sequence starts - connect to instruments"""
        log.info("Connecting to instruments...")
        self._scope, self._pulser = connect_instruments()
        log.info("Instruments connected")

    def execute(self):
        """Execute the 3PP measurement"""
        log.info("Starting 3PP measurement")

        # Use save_directory parameter for custom saving
        results_directory = self.save_directory

        # Run the measurement with persistent connections
        data = run_3pp(
            u_amplitude=self.u_amplitude,
            u_to_n_delay=self.u_to_n_delay,
            nd_amplitude=self.nd_amplitude,
            n_to_d_delay=self.n_to_d_delay,
            polarity=self.polarity,
            base_offset=self.base_offset,
            pulse_width_ns=self.pulse_width_ns,
            capture_width_ns=self.capture_width_ns,
            record_length=self.record_length,
            vdiv=self.vdiv,
            num_averages=self.num_averages,
            save_directory=results_directory,
            auto_trigger=True,
            save_plot=False,
            save_data=True,
            verbose=True,
            scope=self._scope,  # Pass existing connections
            pulser=self._pulser
        )

        # Emit data for live plotting
        if data is not None:
            for i, (t, v) in enumerate(zip(data['time'], data['voltage'])):
                self.emit('results', {
                    'time_ns': t * 1e9,
                    'voltage_V': v,
                })
                # Update progress
                if i % 100 == 0:
                    self.emit('progress', 100 * i / len(data['time']))
                if self.should_stop():
                    log.warning("Measurement aborted by user")
                    break

        log.info("3PP measurement complete")

    def shutdown(self):
        """Called once after sequence completes - close instruments"""
        log.info("Closing instrument connections...")

        if self._scope is not None:
            try:
                self._scope.shutdown()
                log.info("Scope closed")
            except Exception as e:
                log.warning(f"Error closing scope: {e}")
            finally:
                self._scope = None

        if self._pulser is not None:
            try:
                self._pulser.shutdown()
                log.info("Pulser closed")
            except Exception as e:
                log.warning(f"Error closing pulser: {e}")
            finally:
                self._pulser = None


class ThreePulseWindow(ManagedWindow):
    """GUI window for 3PP measurements"""

    def __init__(self):
        super().__init__(
            procedure_class=ThreePulseProcedure,
            inputs=[
                'u_amplitude', 'u_to_n_delay',
                'nd_amplitude', 'n_to_d_delay',
                'polarity', 'base_offset',
                'pulse_width_ns', 'capture_width_ns',
                'record_length', 'vdiv', 'num_averages',
                'save_directory'
            ],
            displays=[
                'u_amplitude', 'nd_amplitude', 'polarity', 'base_offset', 'num_averages'
            ],
            x_axis='time_ns',
            y_axis='voltage_V',
            sequencer=True,
            sequencer_inputs=['u_amplitude', 'nd_amplitude', 'base_offset', 'n_to_d_delay'],
        )
        self.setWindowTitle('3PP Measurement Control')

        # Set default directory to trash folder for PyMeasure's auto-save
        trash_dir = Path("../data/scratch")
        trash_dir.mkdir(parents=True, exist_ok=True)
        self.directory = str(trash_dir)

        # Add scrollbar to inputs
        QtWidgets.QApplication.processEvents()
        for dock in self.findChildren(QtWidgets.QDockWidget):
            widget = dock.widget()
            if widget and hasattr(widget, 'layout'):
                scroll = QtWidgets.QScrollArea()
                scroll.setWidget(widget)
                scroll.setWidgetResizable(True)
                scroll.setMinimumWidth(350)
                dock.setWidget(scroll)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ThreePulseWindow()
    window.show()
    sys.exit(app.exec())