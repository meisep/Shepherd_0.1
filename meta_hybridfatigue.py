"""
Fatigue measurement program - burst mode for low cycle counts, continuous
mode with software timing for increments above CONTINUOUS_MODE_THRESHOLD.

Replaces meta_lowfatigue.py for high-cycle runs. meta_lowfatigue.py is kept
as a fallback in case hardware behavior differs from expectations.
"""
import time
from bnc765_driver import BNC765
from pulse_3pp import run_3pp

BNC765_MAX_BURST_CYCLES = 4.2e9
# Increments larger than this switch from burst to continuous+timed mode.
CONTINUOUS_MODE_THRESHOLD = 1e9


def _setup_ud_channels(pulser, amplitude, pulse_width_ns, spacing_ns, base_offset):
    """
    Shared channel setup for U-D bipolar stress waveform.

    One full fatigue cycle = U pulse + spacing + D pulse + spacing,
    so hardware period = 2 * (pulse_width_ns + spacing_ns).
    """
    period_ns = 2 * (pulse_width_ns + spacing_ns)

    pulser.ch1.output_state = False
    pulser.ch1.pulse_mode = 'SIN'
    pulser.ch1.inverted = False
    pulser.write(f'SOURCE1:PULSE1:WIDTH {pulse_width_ns}E-9')
    pulser.ch1.voltage_level = amplitude
    pulser.ch1.voltage_offset = base_offset + amplitude / 2
    pulser.ch1.load_impedance = 50
    pulser.write(f'SOURCE1:PULSE1:DELAY 0')
    pulser.ch1.period = f'{period_ns}ns'

    pulser.ch2.output_state = False
    pulser.ch2.pulse_mode = 'SIN'
    pulser.ch2.inverted = True
    pulser.write(f'SOURCE2:PULSE1:WIDTH {pulse_width_ns}E-9')
    pulser.ch2.voltage_level = amplitude
    pulser.ch2.voltage_offset = base_offset - amplitude / 2
    pulser.ch2.load_impedance = 50
    pulser.write(f'SOURCE2:PULSE1:DELAY {pulse_width_ns + spacing_ns}E-9')
    pulser.ch2.period = f'{period_ns}ns'

    return period_ns


def setup_fatigue_pulser_burst(pulser, amplitude, pulse_width_ns, spacing_ns,
                               num_cycles, base_offset=0.0, verbose=False):
    pulser.stop()
    period_ns = _setup_ud_channels(pulser, amplitude, pulse_width_ns, spacing_ns, base_offset)

    num_cycles = min(int(num_cycles), int(BNC765_MAX_BURST_CYCLES))
    pulser.ch1.burst_ncycles = num_cycles
    pulser.ch2.burst_ncycles = num_cycles
    pulser.trigger_mode = 'BURST'
    pulser.trigger_source = 'MANUAL'
    pulser.trigger_output_delay = 0

    pulser.ch1.output_state = True
    pulser.ch2.output_state = True
    pulser.start()

    if verbose:
        freq_hz = 1e9 / period_ns
        print(f"Burst mode: {num_cycles:.2e} cycles at {freq_hz/1e6:.3f} MHz "
              f"({num_cycles/freq_hz*1e3:.1f} ms)")


def setup_fatigue_pulser_continuous(pulser, amplitude, pulse_width_ns, spacing_ns,
                                    base_offset=0.0, verbose=False):
    """Configure BNC765 for continuous mode. Caller is responsible for timing the stop."""
    pulser.stop()
    period_ns = _setup_ud_channels(pulser, amplitude, pulse_width_ns, spacing_ns, base_offset)

    pulser.trigger_mode = 'CONTINUOUS'
    pulser.trigger_output_delay = 0

    pulser.ch1.output_state = True
    pulser.ch2.output_state = True
    pulser.start()

    if verbose:
        freq_hz = 1e9 / period_ns
        print(f"Continuous mode: {freq_hz/1e6:.3f} MHz (software-timed stop)")


def generate_measurement_schedule(max_cycles):
    """Generate decade-based measurement schedule [100, 1000, 10000, ...]"""
    schedule = []
    decade = 100
    while decade <= max_cycles:
        schedule.append(int(decade))
        decade *= 10
    return schedule


def apply_stress_increment(pulser, cycles_to_apply, amplitude, pulse_width_ns,
                           spacing_ns, base_offset=0.0, verbose=False):
    """
    Apply stress cycles, choosing burst or continuous mode based on count.

    For continuous mode the cycle count is controlled by a timed sleep.
    Uses the actual hardware period (2*(width+spacing)) for duration math.
    """
    # Actual period of one full U+D bipolar cycle on the hardware
    actual_period_ns = 2 * (pulse_width_ns + spacing_ns)
    actual_freq_hz = 1e9 / actual_period_ns
    duration_s = cycles_to_apply / actual_freq_hz

    if cycles_to_apply <= CONTINUOUS_MODE_THRESHOLD:
        setup_fatigue_pulser_burst(
            pulser=pulser,
            amplitude=amplitude,
            pulse_width_ns=pulse_width_ns,
            spacing_ns=spacing_ns,
            num_cycles=cycles_to_apply,
            base_offset=base_offset,
            verbose=verbose
        )
        pulser.trigger()
        # Sleep is a safety buffer only — burst is self-terminating
        time.sleep(duration_s + 0.5)
    else:
        setup_fatigue_pulser_continuous(
            pulser=pulser,
            amplitude=amplitude,
            pulse_width_ns=pulse_width_ns,
            spacing_ns=spacing_ns,
            base_offset=base_offset,
            verbose=verbose
        )
        if verbose:
            print(f"  Running for {duration_s:.1f} s ({cycles_to_apply:.2e} cycles)...")
        time.sleep(duration_s)

    pulser.ch1.output_state = False
    pulser.ch2.output_state = False
    pulser.stop()
    time.sleep(0.5)


def run_hybridfatigue(
    fatigue_amplitude,
    fatigue_pulse_width_ns,
    fatigue_spacing_ns,
    max_cycles,
    params_3pp,
    save_directory,
    base_offset=0.0,
    verbose=True,
    wait_for_input=True,
):
    """
    Run fatigue measurement with automatic burst/continuous mode switching.

    Stress increments <= CONTINUOUS_MODE_THRESHOLD use burst mode (hardware-counted).
    Larger increments use continuous mode with software-timed stop.

    metadata fatigue_frequency_hz matches meta_lowfatigue.py convention
    (period_ns = width + spacing, not the full 2*(width+spacing) hardware period)
    for backward compatibility with existing analysis.
    """
    # Metadata frequency convention: kept consistent with meta_lowfatigue.py
    metadata_period_ns = fatigue_pulse_width_ns + fatigue_spacing_ns
    metadata_frequency_hz = 1e9 / metadata_period_ns

    schedule = generate_measurement_schedule(max_cycles)

    if verbose:
        actual_period_ns = 2 * (fatigue_pulse_width_ns + fatigue_spacing_ns)
        actual_freq_hz = 1e9 / actual_period_ns
        print(f"\n{'='*60}")
        print(f"FATIGUE MEASUREMENT")
        print(f"{'='*60}")
        print(f"Stress amplitude:   {fatigue_amplitude} V")
        print(f"Actual frequency:   {actual_freq_hz/1e6:.3f} MHz")
        print(f"Max cycles:         {max_cycles:.2e}")
        print(f"Schedule:           {schedule}")
        print(f"Mode threshold:     {CONTINUOUS_MODE_THRESHOLD:.0e} cycles/increment")
        print(f"{'='*60}\n")

    pulser = BNC765("TCPIP::169.254.125.69::INSTR")

    results = {
        'cycles_at_measurement': [],
        'data': {'npp': [], 'pnn': []},
        'fatigue_params': {
            'amplitude': fatigue_amplitude,
            'pulse_width_ns': fatigue_pulse_width_ns,
            'spacing_ns': fatigue_spacing_ns,
            'frequency_hz': metadata_frequency_hz,
        }
    }

    def _measure_3pp(cycle_count):
        for polarity in ['npp', 'pnn']:
            data = run_3pp(
                **params_3pp,
                polarity=polarity,
                save_directory=save_directory,
                auto_trigger=True,
                extra_metadata={
                    'cycle_count': cycle_count,
                    'fatigue_amplitude': fatigue_amplitude,
                    'fatigue_frequency_hz': metadata_frequency_hz,
                }
            )
            results['data'][polarity].append(data)
        results['cycles_at_measurement'].append(cycle_count)

    try:
        if verbose:
            print(f"\n{'='*40}")
            print(f"INITIAL 3PP MEASUREMENT (0 cycles)")
            print(f"{'='*40}")
        if wait_for_input:
            input("Press Enter to start initial 3PP measurement...")

        _measure_3pp(0)
        cycles_applied = 0

        for target_cycles in schedule:
            cycles_to_apply = target_cycles - cycles_applied
            mode = 'burst' if cycles_to_apply <= CONTINUOUS_MODE_THRESHOLD else 'continuous'

            if verbose:
                print(f"\nStress: {cycles_to_apply:.2e} cycles via {mode} mode "
                      f"(total → {target_cycles:.2e})")

            if wait_for_input:
                input(f"Press Enter to apply {cycles_to_apply:.2e} cycles ({mode} mode)...")

            apply_stress_increment(
                pulser=pulser,
                cycles_to_apply=cycles_to_apply,
                amplitude=fatigue_amplitude,
                pulse_width_ns=fatigue_pulse_width_ns,
                spacing_ns=fatigue_spacing_ns,
                base_offset=base_offset,
                verbose=verbose
            )

            cycles_applied = target_cycles

            if verbose:
                print(f"\n{'='*40}")
                print(f"3PP MEASUREMENT at {cycles_applied:.2e} cycles")
                print(f"{'='*40}")
            if wait_for_input:
                input(f"Press Enter to take 3PP at {cycles_applied:.2e} cycles...")

            _measure_3pp(cycles_applied)

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
