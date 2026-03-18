import sys
from pymeasure.display.windows import ManagedWindow
from pymeasure.experiment import Procedure, Results
from pymeasure.experiment import FloatParameter, IntegerParameter, Parameter
import logging
from pulse_uduu_longtime import run_uduu_long
from pymeasure.display.Qt import QtWidgets
from pathlib import Path

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class UDUULongProcedure(Procedure):
    """Procedure for UDUU long-time measurements"""

    # Pulse parameters
    pulse_amplitude = FloatParameter('Pulse Amplitude', units='V', default=0.5)
    pulse_width_ns = FloatParameter('Pulse Width', units='ns', default=200.0)
    u_to_d_delay = FloatParameter('U to D Delay', units='ns', default=200.0)
    d_to_u_delay_s = FloatParameter('D to U Delay', units='s', default=1)
    u_to_u_delay = FloatParameter('U to U Delay', units='ns', default=200.0)
    polarity = Parameter('Polarity', default='pp')

    # Voltage parameters
    base_offset = FloatParameter('Base Offset', units='V', default=0.0)

    # Scope parameters
    capture_width_ns = FloatParameter('Capture Width', units='ns', default=1000.0)
    record_length = IntegerParameter('Record Length', default=10000)
    vdiv = FloatParameter('V/div', units='V', default=0.2)
    num_averages = IntegerParameter('Num Averages', default=4)

    # Saving parameters
    save_directory = Parameter('Save Directory', default='test_uduu')

    # Enable sequencer for these parameters
    SEQUENCER_INPUTS = ['pulse_amplitude', 'd_to_u_delay_s', 'u_to_d_delay', 'base_offset']

    DATA_COLUMNS = ['time_ns', 'voltage_V']

    def execute(self):
        """Execute the UDUU long-time measurement"""
        log.info("Starting UDUU long-time measurement")

        # Use save_directory parameter for custom saving
        results_directory = self.save_directory

        # Run the measurement
        data = run_uduu_long(
            pulse_amplitude=self.pulse_amplitude,
            pulse_width_ns=self.pulse_width_ns,
            u_to_d_delay=self.u_to_d_delay,
            d_to_u_delay_s=self.d_to_u_delay_s,
            u_to_u_delay=self.u_to_u_delay,
            polarity=self.polarity,
            base_offset=self.base_offset,
            capture_width_ns=self.capture_width_ns,
            record_length=self.record_length,
            num_averages=self.num_averages,
            vdiv=self.vdiv,
            save_directory=results_directory,
            auto_trigger=True,
            save_plot=False,
            save_data=True,
            verbose=True
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

        log.info("UDUU long-time measurement complete")


class UDUULongWindow(ManagedWindow):
    """GUI window for UDUU long-time measurements"""

    def __init__(self):
        super().__init__(
            procedure_class=UDUULongProcedure,
            inputs=[
                'pulse_amplitude', 'pulse_width_ns',
                'u_to_d_delay', 'd_to_u_delay_s', 'u_to_u_delay',
                'polarity', 'base_offset',
                'capture_width_ns', 'record_length',
                'vdiv', 'num_averages',
                'save_directory'
            ],
            displays=[
                'pulse_amplitude', 'd_to_u_delay_s', 'polarity', 'base_offset', 'num_averages',
            ],
            x_axis='time_ns',
            y_axis='voltage_V',
            sequencer=True,
            sequencer_inputs=['pulse_amplitude', 'd_to_u_delay_s', 'base_offset'],
        )
        self.setWindowTitle('UDUU Long-Time Measurement Control')

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
    window = UDUULongWindow()
    window.show()
    sys.exit(app.exec())