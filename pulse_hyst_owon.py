"""
Hysteresis loop measurement using the OWON AG3062 AWG + TDS6604 oscilloscope.

The OWON cannot be triggered via VISA, so it runs via its internal timer burst.
Only the sense channel (current through sense resistor) is recorded. The drive
voltage is reconstructed in post-processing from the waveform metadata.

Sequence: configure AWG → configure scope → arm scope → enable AWG → capture.
"""
import time
from owon_ag3062_driver import OWONAG3062
from tds6604_driver import TDS6604
from utils.utilities import save_waveform


def setup_awg_hyst(awg, amplitude, period, ncycles, offset=0.0, channel=1,
                   repeat_rate=None, verbose=False):
    """
    Configure the OWON AWG for a triangle-wave burst.

    Uses RAMP at 50% symmetry (symmetric triangle). Fires every repeat_rate
    seconds via the internal timer. Output is left OFF — caller enables it
    after arming the scope.

    repeat_rate defaults to 2 * ncycles * period so there is a gap between shots.
    """
    ch = awg.ch1 if channel == 1 else awg.ch2

    if repeat_rate is None:
        repeat_rate = 2 * ncycles * period

    ch.output_state = False
    ch.burst_state = False

    ch.waveform = 'RAMP'
    ch.ramp_symmetry = 50.0          # 50% symmetry = symmetric triangle
    ch.frequency = 1.0 / period
    ch.amplitude = 2.0 * amplitude   # OWON takes Vpp; peak amplitude = Vpp/2
    ch.offset = offset
    ch.load_impedance = 'INFinity'   # high-Z for direct connection to device

    ch.burst_mode = 'TRIGgered'
    ch.burst_source = 'TIMer'
    ch.burst_ncycles = ncycles
    ch.burst_internal_period = repeat_rate

    time.sleep(0.5)

    if verbose:
        print(f"AWG CH{channel}: triangle ±{amplitude} V, "
              f"period={period*1e6:.2f} µs, {ncycles} cyc/burst, "
              f"repeat every {repeat_rate*1e3:.1f} ms")


def setup_scope_hyst(scope, period, ncycles, sense_channel=1,
                     vdiv_sense=0.05, record_length=10000,
                     num_averages=1, verbose=False):
    """
    Configure the TDS6604 to capture ncycles of the sense resistor signal.

    Triggers on the sense channel itself: falling edge at -20 mV, which
    catches the current reversal mid-sweep. The drive voltage is not
    connected to the scope — it is reconstructed from metadata in post-processing.
    """
    capture_width_s = ncycles * period

    sense_ch = getattr(scope, f'ch{sense_channel}')
    sense_ch.enabled = True
    sense_ch.coupling = 'DC'
    sense_ch.impedance = 'FIFTY'
    sense_ch.scale = vdiv_sense
    sense_ch.position = 0

    scope.record_length = record_length
    scope.timebase = capture_width_s / 10
    scope.horizontal_position = 0.1 * capture_width_s  # 10% pre-trigger

    scope.setup_edge_trigger(
        source=f'CH{sense_channel}',
        level=-0.02,
        slope='FALL',
        mode='NORMAL'
    )

    if num_averages > 1:
        scope.acquisition_mode = 'AVERAGE'
        scope.write(f'ACQUIRE:NUMAVG {num_averages}')
    else:
        scope.acquisition_mode = 'SAMPLE'

    scope.acquisition_stopafter = 'SEQUENCE'

    if verbose:
        print(f"Scope CH{sense_channel}: {capture_width_s*1e6:.1f} µs capture, "
              f"{record_length} pts, {num_averages}x avg, "
              f"trigger: falling edge at -20 mV")


def run_hyst(amplitude, period, ncycles=1, offset=0.0,
             sense_resistance=1e3,
             awg_channel=1,
             sense_channel=1,
             vdiv_sense=0.05,
             record_length=10000, num_averages=1,
             repeat_rate=None,
             save_directory=None, save_data=True,
             auto_start=False, verbose=False,
             extra_metadata=None):
    """
    Capture a hysteresis loop sense signal using the OWON AWG + TDS6604.

    Only the sense channel (voltage across sense resistor) is recorded.
    The drive voltage waveform is a symmetric triangle and can be reconstructed
    from the metadata: amplitude_V, period_s, offset_V, ncycles, and the
    time axis in the saved CSV.

    Parameters
    ----------
    amplitude       : float — peak voltage of the triangle drive (V)
    period          : float — period of the triangle wave (s)
    ncycles         : int   — number of full cycles to capture
    offset          : float — DC offset of the drive (V)
    sense_resistance: float — sense resistor value in ohms (written to metadata)
    awg_channel     : int   — OWON output channel (1 or 2)
    sense_channel   : int   — scope channel measuring sense resistor voltage
    vdiv_sense      : float — scope V/div for sense channel
    record_length   : int   — scope record length in samples
    num_averages    : int   — number of waveforms to average on scope
    repeat_rate     : float — AWG burst repeat period (s); default 2*ncycles*period
    save_directory  : str   — directory to save CSV
    save_data       : bool  — whether to save data
    auto_start      : bool  — if False, prompts before enabling AWG output
    verbose         : bool  — print progress
    extra_metadata  : dict  — additional key/value pairs written to CSV header

    Returns
    -------
    waveform dict with keys 'time' (s array) and 'voltage' (V array),
    matching the sense channel capture.
    """
    awg = OWONAG3062(OWONAG3062.VISA_ADDRESS)
    scope = TDS6604('GPIB0::2::INSTR')

    if verbose:
        print(f"Connected AWG:   {awg.identify()}")
        print(f"Connected scope: {scope.id}")

    try:
        # 1. Configure AWG (output stays OFF until scope is armed)
        setup_awg_hyst(
            awg, amplitude=amplitude, period=period, ncycles=ncycles,
            offset=offset, channel=awg_channel, repeat_rate=repeat_rate,
            verbose=verbose
        )

        # 2. Configure scope
        setup_scope_hyst(
            scope, period=period, ncycles=ncycles,
            sense_channel=sense_channel,
            vdiv_sense=vdiv_sense,
            record_length=record_length, num_averages=num_averages,
            verbose=verbose
        )

        # 3. Arm the scope — waits for falling edge on sense channel
        scope.arm()
        time.sleep(0.2)

        if not auto_start:
            input("Scope armed. Press Enter to enable AWG output...")

        # 4. Enable AWG — internal timer fires the first burst immediately
        ch = awg.ch1 if awg_channel == 1 else awg.ch2
        ch.burst_state = True
        ch.output_state = True

        if verbose:
            print("AWG running — waiting for scope to trigger...")

        # 5. Wait for capture
        repeat_rate_s = repeat_rate if repeat_rate is not None else 2 * ncycles * period
        timeout = repeat_rate_s + ncycles * period + 2.0

        time.sleep(repeat_rate_s*num_averages) #need to wait for the awg to complete

        if not scope.wait_for_trigger(timeout=timeout):
            raise TimeoutError(
                f"Scope did not trigger within {timeout:.1f} s. "
                "Check connections and sense channel trigger level."
            )

        # 6. Read sense channel only
        sense_data = getattr(scope, f'ch{sense_channel}').get_waveform()

        # 7. Turn AWG off
        ch.burst_state = False
        ch.output_state = False

        if verbose:
            print(f"Captured {len(sense_data['voltage'])} points.")

        # 8. Metadata — enough to reconstruct the triangle drive in post-processing
        metadata = {
            'amplitude_V': amplitude,
            'period_s': period,
            'ncycles': ncycles,
            'offset_V': offset,
            'sense_resistance_ohm': sense_resistance,
            'awg_channel': awg_channel,
            'sense_scope_channel': sense_channel,
            'record_length': record_length,
            'num_averages': num_averages,
            'drive_waveform': 'triangle',  # RAMP 50% symmetry
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        # 9. Save
        if save_data and save_directory is not None:
            amp_str = f"{amplitude:.2f}V".replace('.', 'p')
            per_str = f"{period*1e6:.1f}us".replace('.', 'p')
            filename = f"hyst_{amp_str}_{per_str}"
            save_waveform(
                sense_data,
                filename=filename,
                directory=save_directory,
                format='csv',
                metadata=metadata,
                overwrite=False,
                verbose=verbose
            )

        return sense_data

    finally:
        try:
            ch = awg.ch1 if awg_channel == 1 else awg.ch2
            ch.burst_state = False
            ch.output_state = False
        except Exception:
            pass
        try:
            awg.shutdown()
        except Exception:
            pass
