"""
3PP - Three Pulse Protocol for Ferroelectric Measurements
U pulse, N pulse, D pulse sequence with polarity control
"""
import time
from bnc765_driver import BNC765
from tds6604_driver import TDS6604
from utils.utilities import *


def connect_instruments():
    """Connect to instruments and return handles"""
    # pulser = BNC765("TCPIP::169.254.209.156::INSTR")  # Kepler
    pulser = BNC765("TCPIP::169.254.125.69::INSTR")  # Berkeley
    scope = TDS6604('GPIB0::2::INSTR')  # Kepler is GPIB 1, berkeley is 2
    return scope, pulser


def setup_pulse_channel_3pp(pulser, channel, voltage, offset, capture_width_ns, pulses,
                        inverted=False, verbose=False):
    """Setup pulse channel with minimal output"""
    num_pulses = len(pulses)
    if num_pulses < 1 or num_pulses > 4:
        raise ValueError("Must specify 1-4 pulses")
    pulser.stop()
    ch = getattr(pulser, f'ch{channel}')
    ch.output_state = False
    time.sleep(0.3)
    pulse_mode_map = {1: 'SIN', 2: 'DOU', 3: 'TRI', 4: 'QUAD'}
    ch.pulse_mode = pulse_mode_map[num_pulses]
    time.sleep(0.2)
    ch.inverted = inverted
    ch.voltage_level = voltage
    ch.voltage_offset = offset + voltage / 2 if not inverted else offset - voltage / 2
    ch.load_impedance = 50
    period_ns = capture_width_ns
    ch.period = f'{period_ns}ns'
    time.sleep(0.2)
    for i, pulse in enumerate(pulses):
        pulse_num = i + 1
        width_ns = pulse.get('width_ns', 100)
        delay_ns = pulse.get('delay_ns', 0)
        pulse_prefix = f'SOURCE{channel}:PULSE{pulse_num}'
        pulser.write(f'{pulse_prefix}:WIDTH {width_ns}E-9')
        pulser.write(f'{pulse_prefix}:DELAY {delay_ns}E-9')
    ch.burst_ncycles = 1
    pulser.trigger_mode = 'BURST'
    pulser.trigger_source = 'MANUAL'
    pulser.trigger_output_amplitude = 0.9
    pulser.trigger_output_polarity = 'POSITIVE'
    pulser.trigger_output_delay = 0
    pulser.write(f'TRIGGER:OUTPUT:SOURCE OUT{channel}')
    ch.output_state = True
    pulser.start()
    if verbose:
        print(f"CH{channel}: {num_pulses} pulse(s), {voltage}V")


def setup_scope_3pp(scope, signal_channel, trigger_channel, max_voltage,
                capture_width_ns, record_length, vdiv, num_averages=1, verbose=False):
    """Setup oscilloscope with averaging"""
    sig_ch = getattr(scope, f'ch{signal_channel}')
    sig_ch.enabled = True
    sig_ch.coupling = 'DC'
    sig_ch.impedance = 'FIFTY'
    sig_ch.scale = vdiv
    sig_ch.position = 0
    trig_ch = getattr(scope, f'ch{trigger_channel}')
    trig_ch.enabled = True
    trig_ch.coupling = 'DC'
    trig_ch.impedance = 'FIFTY'
    trig_ch.scale = 0.25
    trig_ch.position = 0
    scope.record_length = record_length
    scope.timebase = capture_width_ns * 1e-9 / 10
    scope.setup_edge_trigger(
        source=f'CH{trigger_channel}',
        level=0.45,
        slope='RISE',
        mode='NORMAL'
    )
    scope.horizontal_position = 0
    if num_averages > 1:
        scope.acquisition_mode = 'AVERAGE'
        scope.write(f'ACQUIRE:NUMAVG {num_averages}')
        if verbose:
            print(f"Scope averaging enabled: {num_averages} acquisitions")
    else:
        scope.acquisition_mode = 'SAMPLE'
    scope.acquisition_stopafter = 'SEQUENCE'
    if verbose:
        print(f"Scope: {scope.timebase * 1e9:.1f} ns/div, {record_length} points, {num_averages}x averaging")


def run_3pp(u_amplitude, u_to_n_delay, nd_amplitude, n_to_d_delay,
            polarity='npp', base_offset=0.0, pulse_width_ns=2.0,
            capture_width_ns=20.0, vdiv=0.5, record_length=10000,
            num_averages=1, save_directory=None, auto_trigger=False,
            save_plot=False, save_data=True, verbose=False,
            scope=None, pulser=None, extra_metadata=None):
    """
    Run 3-Pulse Protocol (3PP) measurement with optional averaging

    Args:
        scope: Optional existing scope connection (for sequence mode)
        pulser: Optional existing pulser connection (for sequence mode)
        num_averages: Number of waveforms to average (1 = no averaging)
        ... (other args same as before)
    """
    if polarity not in ['npp', 'pnn']:
        raise ValueError("polarity must be 'npp' or 'pnn'")

    # Track if we created the connections (so we know whether to close them)
    scope_created = False
    pulser_created = False

    capture_width_ns = 6*pulse_width_ns

    try:
        # Connect to instruments if not provided
        # pulser = BNC765("TCPIP::169.254.209.156::INSTR")  # Kepler
        pulser = BNC765("TCPIP::169.254.125.69::INSTR")  # Berkeley
        scope = TDS6604('GPIB0::2::INSTR')  # Kepler is GPIB 1, berkeley is 2

        if verbose:
            print(f"Connected to: {pulser.id}")
            print(f"Connected to: {scope.id}")
            print(f"Polarity: {polarity}, Averages: {num_averages}")

        # Add a 100ns pre-pulse delay
        PRE_PULSE_DELAY_NS = 100

        n_absolute_delay = pulse_width_ns + u_to_n_delay + PRE_PULSE_DELAY_NS
        d_absolute_delay = n_absolute_delay + pulse_width_ns + n_to_d_delay

        pulses_u = [{'width_ns': pulse_width_ns, 'delay_ns': PRE_PULSE_DELAY_NS}]  # U starts at 100ns
        pulses_nd = [
            {'width_ns': pulse_width_ns, 'delay_ns': n_absolute_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': d_absolute_delay}
        ]
        if polarity == 'npp':
            u_offset = base_offset
            nd_offset = base_offset
            setup_pulse_channel_3pp(
                pulser=pulser, channel=1, voltage=u_amplitude,
                offset=u_offset, inverted=True,
                capture_width_ns=capture_width_ns,
                pulses=pulses_u, verbose=verbose
            )
            setup_pulse_channel_3pp(
                pulser=pulser, channel=2, voltage=nd_amplitude,
                offset=0, inverted=False, # see if we are double counting the offset
                capture_width_ns=capture_width_ns,
                pulses=pulses_nd, verbose=verbose
            )
        else:  # 'pnn'
            u_offset = base_offset
            nd_offset = base_offset
            setup_pulse_channel_3pp(
                pulser=pulser, channel=1, voltage=u_amplitude,
                offset=0, inverted=False,
                capture_width_ns=capture_width_ns,
                pulses=pulses_u, verbose=verbose
            )
            setup_pulse_channel_3pp(
                pulser=pulser, channel=2, voltage=nd_amplitude,
                offset=nd_offset, inverted=True,
                capture_width_ns=capture_width_ns,
                pulses=pulses_nd, verbose=verbose
            )
        max_voltage = max(u_amplitude, nd_amplitude)
        setup_scope_3pp(
            scope=scope, signal_channel=1, trigger_channel=4,
            max_voltage=max_voltage, vdiv=vdiv,
            capture_width_ns=capture_width_ns,
            record_length=record_length,
            num_averages=num_averages, verbose=verbose
        )
        scope.arm()
        if not auto_trigger:
            input("Press Enter to trigger 3PP...")
        else:
            time.sleep(0.2)
            
        # Trigger pulser num_averages times for hardware averaging
        for i in range(num_averages):
            pulser.trigger()
            time.sleep(0.1) # there is probably a smarter way to do this, but I will think about it later

        while scope.acquisition_state:
            # print('cleanup')
            pulser.trigger()
            time.sleep(0.1)

        pulser.ch1.output_state = False
        pulser.ch2.output_state = False
        pulser.stop()

        # Wait for all averages to complete
        timeout = 2 + (num_averages * capture_width_ns * 1e-9)
        if scope.wait_for_trigger(timeout=timeout):
            ch1_data = scope.ch1.get_waveform()
            if verbose:
                print(f"Captured: {len(ch1_data['voltage'])} points (averaged over {num_averages})")
        else:
            raise TimeoutError("Scope trigger timeout during averaging")

        # Generate base filename (with dots replaced by 'p')
        filename = f"3pp_{polarity}_U{u_amplitude:.2f}V_ND{nd_amplitude:.2f}V"
        filename = filename.replace('.', 'p')
        metadata = {
            'u_amplitude': u_amplitude,
            'u_to_n_delay': u_to_n_delay,
            'nd_amplitude': nd_amplitude,
            'n_to_d_delay': n_to_d_delay,
            'polarity': polarity,
            'base_offset': base_offset,
            'pulse_width_ns': pulse_width_ns,
            'capture_width_ns': capture_width_ns,
            'record_length': record_length,
            'num_averages': num_averages,
            'pre_pulse_delay_ns': PRE_PULSE_DELAY_NS,
        }
        # Merge extra metadata if provided
        if extra_metadata is not None:
            metadata.update(extra_metadata)

        if save_data:
            saved_file, dir_path = save_waveform(
                ch1_data,
                filename=filename,
                directory=save_directory,
                format='csv',
                metadata=metadata,
                overwrite=False,
                verbose=verbose
            )
            # Save plot in same directory
            if save_plot:
                plot_path = dir_path / f"{filename}.png"
                plot_waveform(ch1_data, plot_path, verbose=verbose)

        return ch1_data

    finally:
        # Only close instruments if WE created them
        if scope_created and scope is not None:
            try:
                scope.shutdown()
            except Exception as e:
                if verbose:
                    print(f"Warning: Error closing scope: {e}")

        if pulser_created and pulser is not None:
            try:
                pulser.shutdown()
            except Exception as e:
                if verbose:
                    print(f"Warning: Error closing pulser: {e}")
