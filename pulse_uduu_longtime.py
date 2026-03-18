"""
UDUU - Four Pulse Protocol for Ferroelectric Measurements
U-D-U-U pulse sequence with Python-timed delay between UD and UU stages
"""
import time
import numpy as np
import matplotlib.pyplot as plt
from bnc765_driver import BNC765
from tds6604_driver import TDS6604
from pathlib import Path
from datetime import datetime
from pulse_3pp import save_waveform

def setup_pulse_channel(pulser, channel, voltage, offset, capture_width_ns, pulses,
                        inverted=False, verbose=False):
    """Setup pulse channel with minimal output"""
    num_pulses = len(pulses)
    if num_pulses < 1 or num_pulses > 4:
        raise ValueError("Must specify 1-4 pulses")
    pulser.stop()
    ch = getattr(pulser, f'ch{channel}')
    ch.output_state = False
    # time.sleep(0.3)
    pulse_mode_map = {1: 'SIN', 2: 'DOU', 3: 'TRI', 4: 'QUAD'}
    ch.pulse_mode = pulse_mode_map[num_pulses]
    # time.sleep(0.2)
    ch.inverted = inverted
    ch.voltage_level = voltage
    ch.voltage_offset = offset + voltage / 2 if not inverted else offset - voltage / 2
    ch.load_impedance = 50
    period_ns = capture_width_ns
    ch.period = f'{period_ns}ns'
    # time.sleep(0.2)
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
        print(f"CH{channel}: {num_pulses} pulse(s), {voltage}V")

def setup_pulse_short(pulser, channel, voltage, offset, capture_width_ns, pulses,
                        inverted=False, verbose=False):
    num_pulses = len(pulses)
    if num_pulses < 1 or num_pulses > 4:
        raise ValueError("Must specify 1-4 pulses")
    ch = getattr(pulser, f'ch{channel}')
    ch.output_state = False
    pulse_mode_map = {1: 'SIN', 2: 'DOU', 3: 'TRI', 4: 'QUAD'}
    ch.pulse_mode = pulse_mode_map[num_pulses]
    ch.inverted = inverted
    ch.voltage_level = voltage
    ch.voltage_offset = offset + voltage / 2 if not inverted else offset - voltage / 2
    ch.period = f'{capture_width_ns}ns'
    for i, pulse in enumerate(pulses):
        pulse_num = i + 1
        width_ns = pulse.get('width_ns', 100)
        delay_ns = pulse.get('delay_ns', 0)
        pulse_prefix = f'SOURCE{channel}:PULSE{pulse_num}'
        pulser.write(f'{pulse_prefix}:WIDTH {width_ns}E-9')
        pulser.write(f'{pulse_prefix}:DELAY {delay_ns}E-9')
    ch.output_state = True

def setup_scope(scope, signal_channel, trigger_channel, max_voltage,
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
        level=1.0, #set this to larger
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
        print(f"Scope: {scope.timebase * 1e9:.1f} ns/div, {record_length} points")

def run_uduu_long(pulse_amplitude, pulse_width_ns, u_to_d_delay, d_to_u_delay_s, u_to_u_delay,
             polarity='nn', base_offset=0.0, capture_width_ns=2000.0, vdiv=0.5,
             record_length=10000, num_averages=1, save_directory=None, auto_trigger=False,
             save_plot=False, save_data=True, verbose=False):
    """
    Run UDUU 4-Pulse Protocol measurement with Python-timed delay
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
            print(f"Polarity: {polarity}, Averages: {num_averages}")

        # Calculate pulse timing
        d_delay = pulse_width_ns + u_to_d_delay
        ud_period_ns = 5 * pulse_width_ns + u_to_d_delay
        uu_period_ns = 5 * pulse_width_ns + u_to_u_delay

        # Determine polarity
        if polarity == 'pp':
            u_inverted = False
            d_inverted = True
        else:  # 'nn'
            u_inverted = True
            d_inverted = False

        u_offset = base_offset
        d_offset = base_offset

        # ========== Setup Scope with Averaging ==========
        setup_scope(
            scope=scope,
            signal_channel=1,
            trigger_channel=4,
            max_voltage=pulse_amplitude,
            capture_width_ns=capture_width_ns,
            record_length=record_length,
            vdiv=vdiv,
            num_averages=num_averages,
            verbose=verbose
        )

        # Load UD Pulses
        pulses_u1 = [{'width_ns': pulse_width_ns, 'delay_ns': 0}]
        pulses_d = [{'width_ns': pulse_width_ns, 'delay_ns': d_delay}]

        # Calculate before the timing-critical section
        u2_delay = 100e-9
        u3_delay = (pulse_width_ns + u_to_u_delay + 100) * 1e-9
        target_delay_s = d_to_u_delay_s
        dummy_delay = u3_delay + 2 * pulse_width_ns * 1e-9

        setup_pulse_channel(
            pulser=pulser, channel=2, voltage=pulse_amplitude,
            offset=d_offset, inverted=d_inverted,
            capture_width_ns=ud_period_ns,
            pulses=pulses_d, verbose=False
        )

        setup_pulse_channel(
            pulser=pulser, channel=1, voltage=pulse_amplitude,
            offset=u_offset, inverted=u_inverted,
            capture_width_ns=ud_period_ns,
            pulses=pulses_u1, verbose=False
        )
        # pulser.trigger_output_polarity = 'NEGATIVE'

        # Arm Scope
        scope.timebase = capture_width_ns * 1e-9 / 10
        scope.arm()

        # ========== AVERAGING LOOP - Repeat entire sequence ==========
        for avg_num in range(num_averages):  # Start from 1 instead of 0
            if verbose:
                print(f"\nAverage {avg_num}/{num_averages}")

            if avg_num !=0:
                pulser.trigger_output_amplitude = 0.9

                setup_pulse_short(
                    pulser=pulser, channel=1, voltage=pulse_amplitude,
                    offset=u_offset, inverted=u_inverted,
                    capture_width_ns=ud_period_ns,
                    pulses=pulses_u1, verbose=False
                )

                setup_pulse_short(
                    pulser=pulser, channel=2, voltage=pulse_amplitude,
                    offset=d_offset, inverted=d_inverted,
                    capture_width_ns=ud_period_ns,
                    pulses=pulses_d, verbose=False
                )
                # pulser.trigger_output_polarity = 'NEGATIVE'

            # Trigger UD Pulses
            if not auto_trigger and avg_num == 1:  # Check for first iteration
                input("Press Enter to start averaging sequence...")

            pulser.trigger()

            # pulser.ch2.voltage_offset = 0
            pulser.ch2.voltage_level = 0.1
            pulser.ch2.pulse_width = 1e-9
            pulser.ch2.pulse_delay = dummy_delay
            pulser.write(f'OUTPUT1:PULSE:MODE DOU')
            pulser.write(f'SOURCE1:PULSE1:WIDTH {pulse_width_ns}E-9')
            pulser.write(f'SOURCE1:PULSE1:DELAY {u2_delay}')
            pulser.write(f'SOURCE1:PULSE2:WIDTH {pulse_width_ns}E-9')
            pulser.write(f'SOURCE1:PULSE2:DELAY {u3_delay}')
            # pulser.trigger_output_polarity = 'POSITIVE'
            pulser.trigger_output_amplitude = 1.5

            # Python Delay
            time.sleep(target_delay_s)

            # Trigger UU Pulses
            pulser.trigger()

            time.sleep(1)

        # Get averaged waveform
        ch1_data = scope.ch1.get_waveform()

        if verbose:
            print(f"\nCaptured: {len(ch1_data['voltage'])} points (averaged over {num_averages})")

        # Generate filename
        filename = f"uduu_{polarity}_A{pulse_amplitude}V_DU{d_to_u_delay_s}s"
        filename = filename.replace('.', 'p')

        metadata = {
            'pulse_amplitude': pulse_amplitude,
            'pulse_width_ns': pulse_width_ns,
            'u_to_d_delay': u_to_d_delay,
            'd_to_u_delay_s': d_to_u_delay_s,
            'u_to_u_delay': u_to_u_delay,
            'polarity': polarity,
            'base_offset': base_offset,
            'capture_width_ns': capture_width_ns,
            'record_length': record_length,
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


    finally:
        pulser.ch1.output_state = False
        pulser.ch2.output_state = False
        pulser.stop()
        pulser.shutdown()
        scope.shutdown()