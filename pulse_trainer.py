"""
UD4 - Eight Pulse Protocol for Ferroelectric Training
(U-D)x4 pulse sequence that captures all eight pulses to check leakage
"""
import time
from bnc765_driver import BNC765
from tds6604_driver import TDS6604
from utils.utilities import save_waveform


def setup_pulse_channel(pulser, channel, voltage, offset, capture_width_ns, pulses,
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
    ch.voltage_offset = offset + voltage/2 if not inverted else offset - voltage/2
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
    pulser.write(f'TRIGGER:OUTPUT:SOURCE OUT{channel}')

    ch.output_state = True
    pulser.start()

    if verbose:
        print(f"CH{channel}: {num_pulses} pulse(s), {voltage}V, inverted={inverted}")


def setup_scope_ud4(scope, signal_channel, trigger_channel, max_voltage,
                     capture_width_ns, record_length, vdiv,
                     delay_seconds, verbose=False):
    """Setup oscilloscope to capture 2x4 pulses"""
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
        mode='NORMAL',
        delay=False,  # Enable horizontal delay
    )


    scope.acquisition_mode = 'SAMPLE'
    scope.acquisition_stopafter = 'SEQUENCE'

    if verbose:
        print(f"Scope: {scope.timebase*1e9:.1f} ns/div, {record_length} points")


def run_ud4(pulse_amplitude, pulse_width_ns, inter_pulse_delay,
            polarity='nn', base_offset=0.0, capture_width_ns=2000.0, vdiv=0.5,
            record_length=10000, num_averages=1, save_directory=None,
            auto_trigger=False, save_plot=False, save_data=True, verbose=False):
    """
    Run (U-D)x4 Eight Pulse Priming Protocol

    Args:
        pulse_amplitude: Pulse amplitude (V), same for all pulses
        pulse_width_ns: Pulse width (ns), same for all pulses
        inter_pulse_delay: Time between each pulse (ns), same for all gaps
        polarity: 'nn' (U negative, D positive) or 'pp' (U positive, D negative)
        base_offset: DC voltage offset (V)
        capture_width_ns: Total capture window (ns) - should cover all 8 pulses
        vdiv: Oscilloscope V/div
        record_length: Number of scope points
        num_averages: Number of waveforms to average
        save_directory: Directory to save data
        auto_trigger: Auto-trigger or wait for user
        save_plot: Save plot to file
        save_data: Save data to CSV
        verbose: Print detailed info

    Returns:
        dict: Waveform data

    Note:
        - CH1 carries 4x U pulses, CH2 carries 4x D pulses [6]
        - Both channels fire on same trigger
        - Maximum 4 pulses per channel on BNC765 [6]
        - U and D pulses interleave to create (U-D)x4 sequence
    """
    if polarity not in ['nn', 'pp']:
        raise ValueError("polarity must be 'nn' or 'pp'")

    pulser = BNC765("TCPIP::169.254.125.69::INSTR")  # Berkeley
    scope = TDS6604('GPIB0::2::INSTR')

    try:
        if verbose:
            print(f"Connected to: {pulser.id}")
            print(f"Connected to: {scope.id}")
            print(f"Polarity: {polarity}, Averages: {num_averages}")

        # Calculate absolute pulse timing for interleaved U-D-U-D-U-D-U-D sequence
        # Each pulse = pulse_width_ns, followed by inter_pulse_delay before the next
        step = pulse_width_ns + inter_pulse_delay  # Time from start of one pulse to start of next

        # U pulses on CH1: positions 0, 2, 4, 6 (every other pulse)
        u1_delay = 0
        u2_delay = 2 * step
        u3_delay = 4 * step
        u4_delay = 6 * step

        # D pulses on CH2: positions 1, 3, 5, 7 (every other pulse, offset by 1 step)
        d1_delay = step
        d2_delay = 3 * step
        d3_delay = 5 * step
        d4_delay = 7 * step

        # Total period: must cover all 8 pulses plus margin
        total_period_ns = 8 * step + pulse_width_ns + 100

        if verbose:
            print(f"\nPulse timing:")
            print(f"  Step: {step:.1f} ns")
            print(f"  U pulses at: {u1_delay:.1f}, {u2_delay:.1f}, {u3_delay:.1f}, {u4_delay:.1f} ns")
            print(f"  D pulses at: {d1_delay:.1f}, {d2_delay:.1f}, {d3_delay:.1f}, {d4_delay:.1f} ns")
            print(f"  Total period: {total_period_ns:.1f} ns")

        # Determine polarity offsets
        if polarity == 'pp':
            u_inverted = False
            d_inverted = True
        else:  # 'nn'
            u_inverted = True
            d_inverted = False

        u_offset = base_offset
        d_offset = base_offset

        # CH1: 4x U pulses [6]
        pulses_u = [
            {'width_ns': pulse_width_ns, 'delay_ns': u1_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': u2_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': u3_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': u4_delay}
        ]

        # CH2: 4x D pulses [6]
        pulses_d = [
            {'width_ns': pulse_width_ns, 'delay_ns': d1_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': d2_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': d3_delay},
            {'width_ns': pulse_width_ns, 'delay_ns': d4_delay}
        ]

        setup_pulse_channel(
            pulser=pulser, channel=1, voltage=pulse_amplitude,
            offset=u_offset, inverted=u_inverted,
            capture_width_ns=total_period_ns,
            pulses=pulses_u, verbose=verbose
        )

        setup_pulse_channel(
            pulser=pulser, channel=2, voltage=pulse_amplitude,
            offset=d_offset, inverted=d_inverted,
            capture_width_ns=total_period_ns,
            pulses=pulses_d, verbose=verbose
        )

        # Setup scope to capture all 8 pulses
        setup_scope_ud4(
            scope=scope,
            signal_channel=1,
            trigger_channel=4,
            capture_width_ns=capture_width_ns,
            record_length=record_length,
            vdiv=vdiv,
            num_averages=num_averages,
            verbose=verbose
        )

        # Arm scope ONCE before averaging loop
        scope.arm()

        if not auto_trigger:
            input("Press Enter to trigger UD4...")

        # Averaging loop - repeat entire sequence num_averages times
        for avg_num in range(num_averages):
            if verbose and num_averages > 1:
                print(f"\nAverage {avg_num + 1}/{num_averages}")

            pulser.trigger()

            # Wait for scope to process before next average
            if avg_num < num_averages - 1:
                time.sleep(0.3)

        # Wait for scope to complete acquisition
        if scope.wait_for_trigger(timeout=5):
            ch1_data = scope.ch1.get_waveform()

            if verbose:
                print(f"\nCaptured: {len(ch1_data['voltage'])} points, "
                      f"{ch1_data['voltage'].min():.3f} to "
                      f"{ch1_data['voltage'].max():.3f} V")

            # Generate filename
            filename = f"ud4_{polarity}_A{pulse_amplitude}V_W{pulse_width_ns}ns"
            filename = filename.replace('.', 'p')

            metadata = {
                'pulse_amplitude': pulse_amplitude,
                'pulse_width_ns': pulse_width_ns,
                'inter_pulse_delay': inter_pulse_delay,
                'polarity': polarity,
                'base_offset': base_offset,
                'capture_width_ns': capture_width_ns,
                'record_length': record_length,
                'num_averages': num_averages,
                'total_period_ns': total_period_ns
            }

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

                if save_plot:
                    from pulse_3pp import plot_waveform
                    plot_path = dir_path / f"{filename}.png"
                    plot_waveform(ch1_data, plot_path, verbose=verbose)

            return ch1_data
        else:
            raise TimeoutError("Scope timeout - no trigger received")

    finally:
        pulser.ch1.output_state = False
        pulser.ch2.output_state = False
        pulser.stop()
        pulser.shutdown()
        scope.shutdown()