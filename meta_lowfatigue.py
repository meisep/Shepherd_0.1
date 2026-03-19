"""
Fatigue measurement program - BURST MODE ONLY (for debugging)
Applies U-D stress cycling using burst mode and takes 3PP measurements at decade intervals
"""
import time
from bnc765_driver import BNC765
from pulse_3pp import run_3pp

BNC765_MAX_BURST_CYCLES = 4.2e9
def setup_fatigue_pulser_burst(pulser, amplitude, pulse_width_ns, spacing_ns,
                               num_cycles, base_offset=0.0, verbose=False):
    pulser.stop()
    period_ns = 2 * (pulse_width_ns + spacing_ns)

    # Cap cycles at hardware maximum [6]
    num_cycles = min(int(num_cycles), BNC765_MAX_BURST_CYCLES)

    # CH1: U pulses (positive) - start at t=0
    pulser.ch1.output_state = False
    pulser.ch1.pulse_mode = 'SIN'
    pulser.ch1.inverted = False
    pulser.write(f'SOURCE1:PULSE1:WIDTH {pulse_width_ns}E-9')  # Width before period [6]
    pulser.ch1.voltage_level = amplitude
    pulser.ch1.voltage_offset = base_offset + amplitude / 2
    pulser.ch1.load_impedance = 50
    pulser.write(f'SOURCE1:PULSE1:DELAY 0')
    pulser.ch1.period = f'{period_ns}ns'

    # CH2: D pulses (negative) - start after U pulse + spacing
    pulser.ch2.output_state = False
    pulser.ch2.pulse_mode = 'SIN'
    pulser.ch2.inverted = True
    pulser.write(f'SOURCE2:PULSE1:WIDTH {pulse_width_ns}E-9')  # Width before period [6]
    pulser.ch2.voltage_level = amplitude
    pulser.ch2.voltage_offset = base_offset - amplitude / 2
    pulser.ch2.load_impedance = 50
    pulser.write(f'SOURCE2:PULSE1:DELAY {pulse_width_ns + spacing_ns}E-9')
    pulser.ch2.period = f'{period_ns}ns'

    # Set burst mode with capped cycle count [6]
    pulser.ch1.burst_ncycles = num_cycles
    pulser.ch2.burst_ncycles = num_cycles
    pulser.trigger_mode = 'BURST'
    pulser.trigger_source = 'MANUAL'
    pulser.trigger_output_delay = 0

    pulser.ch1.output_state = True
    pulser.ch2.output_state = True
    pulser.start()

    if verbose:
        frequency_hz = 1e9 / period_ns
        duration_s = num_cycles / frequency_hz
        print(f"Burst mode configured:")
        print(f"  Amplitude: {amplitude} V")
        print(f"  Cycles: {num_cycles} (max: {BNC765_MAX_BURST_CYCLES:.2e})")
        print(f"  Period: {period_ns} ns")
        print(f"  Frequency: {frequency_hz / 1e6:.3f} MHz")
        print(f"  Duration: {duration_s:.3f} s")


def generate_measurement_schedule(max_cycles):
    """
    Generate decade-based measurement schedule

    Args:
        max_cycles: Maximum number of cycles

    Returns:
        list: Cycle counts at each measurement point [100, 1000, 10000, ...]
    """
    schedule = []
    decade = 100
    while decade <= max_cycles:
        schedule.append(int(decade))
        decade *= 10
    return schedule


def run_fatigue_burst(
    fatigue_amplitude,
    fatigue_pulse_width_ns,
    fatigue_spacing_ns,
    max_cycles,
    params_3pp,
    save_directory,
    base_offset=0.0,
    verbose=True,
    wait_for_input=True,  # Add this parameter to easily disable later
):
    period_ns = fatigue_pulse_width_ns + fatigue_spacing_ns
    frequency_hz = 1e9 / period_ns
    schedule = generate_measurement_schedule(max_cycles)

    if verbose:
        print(f"\n{'='*60}")
        print(f"FATIGUE MEASUREMENT - BURST MODE DEBUG")
        print(f"{'='*60}")
        print(f"Stress amplitude: {fatigue_amplitude} V")
        print(f"Stress frequency: {frequency_hz/1e6:.3f} MHz")
        print(f"Max cycles: {max_cycles:.2e}")
        print(f"Measurement schedule: {schedule}")
        print(f"{'='*60}\n")

    pulser = BNC765("TCPIP::169.254.125.69::INSTR")

    results = {
        'cycles_at_measurement': [],
        'data': {'npp': [], 'pnn': []},
        'fatigue_params': {
            'amplitude': fatigue_amplitude,
            'pulse_width_ns': fatigue_pulse_width_ns,
            'spacing_ns': fatigue_spacing_ns,
            'frequency_hz': frequency_hz,
        }
    }

    try:
        # Initial 3PP measurement at 0 cycles
        if verbose:
            print(f"\n{'='*40}")
            print(f"INITIAL 3PP MEASUREMENT (0 cycles)")
            print(f"{'='*40}")

        if wait_for_input:
            input("Press Enter to start initial 3PP measurement...")

        for polarity in ['npp', 'pnn']:
            data = run_3pp(
                **params_3pp,
                polarity=polarity,
                save_directory=save_directory,
                auto_trigger=True,
                extra_metadata={
                    'cycle_count': 0,
                    'fatigue_amplitude': fatigue_amplitude,
                    'fatigue_frequency_hz': frequency_hz
                }
            )
            results['data'][polarity].append(data)

        results['cycles_at_measurement'].append(0)
        cycles_applied = 0

        for target_cycles in schedule:
            cycles_to_apply = target_cycles - cycles_applied
            duration_s = cycles_to_apply / frequency_hz

            if verbose:
                print(f"\nConfiguring burst: {cycles_to_apply} cycles "
                      f"({duration_s*1e3:.3f} ms) "
                      f"to reach {target_cycles:.2e} total...")

            # Configure burst [3][6]
            setup_fatigue_pulser_burst(
                pulser=pulser,
                amplitude=fatigue_amplitude,
                pulse_width_ns=fatigue_pulse_width_ns,
                spacing_ns=fatigue_spacing_ns,
                num_cycles=cycles_to_apply,
                base_offset=base_offset,
                verbose=verbose
            )

            # Wait for user to verify pulse setup on front panel [3]
            if wait_for_input:
                input(f"Check pulser setup for {cycles_to_apply} cycles. "
                      f"Press Enter to trigger burst...")

            # Trigger burst [3]
            pulser.trigger()

            # Wait for burst to complete
            time.sleep(duration_s + 0.1)

            pulser.ch1.output_state = False
            pulser.ch2.output_state = False
            pulser.stop()
            time.sleep(0.5)

            cycles_applied = target_cycles

            if verbose:
                print(f"\n{'='*40}")
                print(f"3PP MEASUREMENT at {cycles_applied:.2e} cycles")
                print(f"{'='*40}")

            # Wait for user to verify scope/pulser for 3PP [3]
            if wait_for_input:
                input(f"Ready to take 3PP measurement at {cycles_applied:.2e} cycles. "
                      f"Press Enter to continue...")

            for polarity in ['npp', 'pnn']:
                data = run_3pp(
                    **params_3pp,
                    polarity=polarity,
                    save_directory=save_directory,
                    auto_trigger=True,
                    extra_metadata={
                        'cycle_count': cycles_applied,
                        'fatigue_amplitude': fatigue_amplitude,
                        'fatigue_frequency_hz': frequency_hz
                    }
                )
                results['data'][polarity].append(data)

            results['cycles_at_measurement'].append(cycles_applied)

        if verbose:
            print(f"\n{'='*60}")
            print(f"FATIGUE MEASUREMENT COMPLETE")
            print(f"Total cycles: {cycles_applied:.2e}")
            print(f"Measurements taken: {len(results['cycles_at_measurement'])}")
            print(f"{'='*60}\n")

        return results

    except KeyboardInterrupt:
        print("\nFatigue measurement interrupted by user")
        return results

    finally:
        try:
            pulser.ch1.output_state = False
            pulser.ch2.output_state = False
            pulser.stop()
            pulser.shutdown()
        except:
            pass
