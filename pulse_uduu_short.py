"""
UDUU - Four Pulse Protocol for Ferroelectric Measurements
using the scope clock- problems with desyncing faster than 5 ms
U-D-U-U pulse sequence with timeout triggering to capture final two U pulses
"""
import time
import numpy as np
import matplotlib.pyplot as plt
from bnc765_driver import BNC765
from tds6604_driver import TDS6604
from pathlib import Path
from datetime import datetime


def setup_pulse_uduu(pulser, channel, voltage, offset, capture_width_ns, pulses, trigger_delay_s,
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

    pulser.trigger_output_delay = trigger_delay_s

    ch.output_state = True
    pulser.start()

    if verbose:
        print(f"CH{channel}: {num_pulses} pulse(s), {voltage}V, inverted={inverted}")


def setup_scope_uduu(scope, signal_channel, trigger_channel,
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



def run_uduu(pulse_amplitude, pulse_width_ns, u_to_d_delay, d_to_u_delay, u_to_u_delay,
             polarity='nn', base_offset=0.0, capture_width_ns=2000.0, vdiv=0.5, num_averages=1,
             record_length=10000, save_directory=None, auto_trigger=False,
             save_plot=False, save_data=True, verbose=False):
    """
    Run UDUU 4-Pulse Protocol measurement

    Args:
        pulse_amplitude: Pulse amplitude (V), same for all pulses
        pulse_width_ns: Pulse width (ns), same for all pulses
        u_to_d_delay: Time between first U and D pulse (ns)
        d_to_u_delay: Time between D and second U pulse (ns) - this is the long delay
        u_to_u_delay: Time between second U and third U pulse (ns)
        polarity: 'nn' (neg-pos-neg-neg) or 'pp' (pos-neg-pos-pos)
        base_offset: DC voltage offset (V)
        capture_width_ns: Capture window for final 2 U pulses (ns)
        vdiv: Oscilloscope V/div
        record_length: Number of scope points
        save_directory: Directory to save data
        auto_trigger: Auto-trigger or wait for user
        save_plot: Save plot to file
        save_data: Save data to CSV
        verbose: Print detailed info

    Returns:
        dict: Waveform data

    Note:
        - Uses timeout trigger to skip first U-D-U sequence
        - Only captures final two U pulses with high resolution
        - d_to_u_delay should be >> u_to_d_delay for timeout trigger to work
    """
    if polarity not in ['nn', 'pp']:
        raise ValueError("polarity must be 'nn' or 'pp'")

    # pulser = BNC765("TCPIP::169.254.209.156::INSTR")  # Kepler
    pulser = BNC765("TCPIP::169.254.125.69::INSTR")  # Berkeley
    scope = TDS6604('GPIB0::2::INSTR')  # Kepler is GPIB 1, berkeley is 2

    try:
        if verbose:
            print(f"Connected to: {pulser.id}")
            print(f"Connected to: {scope.id}")
            print(f"Polarity: {polarity}")

        # Calculate absolute pulse timing
        # U1 at t=0
        d_delay = pulse_width_ns + u_to_d_delay
        # U2 at t = U1_width + u_to_d + D_width + d_to_u
        u2_delay = d_delay + pulse_width_ns + d_to_u_delay
        # U3 at t = U2_start + U2_width + u_to_u
        u3_delay = u2_delay + pulse_width_ns + u_to_u_delay

        # Setup pulses on two channels
        # Channel 1: U pulses (3 pulses: U1, U2, U3)
        pulses_u = [
            {'width_ns': pulse_width_ns, 'delay_ns': 0},           # U1
            {'width_ns': pulse_width_ns, 'delay_ns': u2_delay},    # U2
            {'width_ns': pulse_width_ns, 'delay_ns': u3_delay}     # U3
        ]

        # Channel 2: D pulse (1 pulse)
        pulses_d = [
            {'width_ns': pulse_width_ns, 'delay_ns': d_delay}      # D
        ]

        # Calculate total period for pulser (must be longer than all pulses)
        total_period_ns = u3_delay + pulse_width_ns + 100  # Add margin

        if polarity == 'pp':
            # U positive, D negative
            u_offset = base_offset
            d_offset = 0
            u_inverted = False
            d_inverted = True
        else:  # 'nn'
            # U negative, D positive
            u_offset = 0
            d_offset = base_offset
            u_inverted = True
            d_inverted = False

        trigger_delay_s = (pulse_width_ns + u_to_d_delay +
                           pulse_width_ns + d_to_u_delay - 200) * 1e-9

        setup_pulse_uduu(
            pulser=pulser, channel=1, voltage=pulse_amplitude,
            offset=u_offset, inverted=u_inverted,
            capture_width_ns=total_period_ns,
            pulses=pulses_u, trigger_delay_s = trigger_delay_s,
            verbose=verbose
        )

        setup_pulse_uduu(
            pulser=pulser, channel=2, voltage=pulse_amplitude,
            offset=d_offset, inverted=d_inverted,
            capture_width_ns=total_period_ns,
            pulses=pulses_d, trigger_delay_s = trigger_delay_s,
            verbose=verbose
        )

        # Calculate timeout for scope trigger
        # Should trigger after U1-D-U2 sequence completes
        # Set timeout slightly less than d_to_u_delay so it triggers during the long gap

        setup_scope_uduu(
            scope=scope,
            signal_channel=1,
            trigger_channel=4,
            vdiv=vdiv,
            capture_width_ns=capture_width_ns,
            record_length=record_length,
            verbose=verbose,
            num_averages=num_averages,
        )

        scope.arm()

        if not auto_trigger:
            input("Press Enter to trigger UDUU...")
        else:
            time.sleep(0.5)

        # ========== AVERAGING LOOP ==========
        for avg_num in range(num_averages):
            # Trigger pulser
            pulser.trigger()
            time.sleep(0.1)

        while scope.acquisition_state:
            # print('cleanup')
            pulser.trigger()
            time.sleep(0.1)

        pulser.ch1.output_state = False
        pulser.ch2.output_state = False
        pulser.stop()

        # Wait for timeout trigger
        if scope.wait_for_trigger(timeout=5):
            ch1_data = scope.ch1.get_waveform()

            if verbose:
                print(f"Captured: {len(ch1_data['voltage'])} points, "
                      f"{ch1_data['voltage'].min():.3f} to {ch1_data['voltage'].max():.3f} V")

            # Generate filename
            filename = f"uduu_{polarity}_A{pulse_amplitude}V_DU{d_to_u_delay}ns"
            filename = filename.replace('.', 'p')

            metadata = {
                'pulse_amplitude': pulse_amplitude,
                'pulse_width_ns': pulse_width_ns,
                'u_to_d_delay': u_to_d_delay,
                'd_to_u_delay': d_to_u_delay,
                'u_to_u_delay': u_to_u_delay,
                'polarity': polarity,
                'base_offset': base_offset,
                'capture_width_ns': capture_width_ns,
                'record_length': record_length,
                'trigger_delay_ns': trigger_delay_s * 1e9,
                'd_to_u_delay_s': trigger_delay_s,
            }

            if save_data:
                from pulse_3pp import save_waveform
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
        pulser.shutdown()
        scope.shutdown()
