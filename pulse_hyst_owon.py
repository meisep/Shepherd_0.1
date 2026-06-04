"""
Hysteresis loop measurement using the OWON AG3062 AWG + TDS6604 oscilloscope.

The OWON cannot be triggered via VISA, so it runs via its internal timer burst.
Sequence: configure both instruments → arm scope → enable AWG output → capture.
"""
import time
from owon_ag3062_driver import OWONAG3062
from tds6604_driver import TDS6604
from utils.utilities import save_waveform


def setup_awg_hyst(awg, amplitude, period, ncycles, offset=0.0, channel=1,
                   repeat_rate=None, verbose=False):
    """
    Configure the OWON AWG for a triangle-wave burst.

    The AWG fires a burst every repeat_rate seconds via its internal timer.
    repeat_rate defaults to 2 * ncycles * period to leave a gap between shots.
    The output is left OFF — caller enables it after arming the scope.
    """
    ch = awg.ch1 if channel == 1 else awg.ch2

    if repeat_rate is None:
        repeat_rate = 2 * ncycles * period

    ch.output_state = False
    ch.burst_state = False

    ch.waveform = 'RAMP'
    ch.ramp_symmetry = 50.0          # 50% symmetry = symmetric triangle wave
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


def setup_scope_hyst(scope, amplitude, period, ncycles,
                     drive_channel=1, sense_channel=2,
                     vdiv_drive=None, vdiv_sense=0.05,
                     record_length=10000, num_averages=1, verbose=False):
    """
    Configure the TDS6604 scope to capture ncycles of the triangle waveform.

    drive_channel : scope channel watching the AWG output voltage
    sense_channel : scope channel watching the sense resistor voltage
    trigger_channel : which scope channel to trigger on (usually same as drive)
    vdiv_drive : V/div for drive channel; defaults to amplitude/4 (fits ±amplitude in ±5 div)
    vdiv_sense : V/div for sense channel
    """
    if vdiv_drive is None:
        vdiv_drive = amplitude / 4.0

    capture_width_s = ncycles * period

    drive_ch = getattr(scope, f'ch{drive_channel}')
    drive_ch.enabled = True
    drive_ch.coupling = 'DC'
    drive_ch.impedance = 'FIFTY'
    drive_ch.scale = vdiv_drive
    drive_ch.position = 0

    sense_ch = getattr(scope, f'ch{sense_channel}')
    sense_ch.enabled = True
    sense_ch.coupling = 'DC'
    sense_ch.impedance = 'FIFTY'
    sense_ch.scale = vdiv_sense
    sense_ch.position = 0

    # Timebase: capture_width / 10 divisions, with a 10% pre-trigger margin
    scope.record_length = record_length
    scope.timebase = capture_width_s / 10
    scope.horizontal_position = 0.1 * capture_width_s  # pre-trigger

    # Trigger on the falling edge of the drive channel at -20 mV
    scope.setup_edge_trigger(
        source=f'CH{drive_channel}',
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
        print(f"Scope: {capture_width_s*1e6:.1f} µs capture, "
              f"{record_length} pts, {num_averages}x avg, "
              f"trigger: CH{drive_channel} falling edge at -20 mV")


def run_hyst(amplitude, period, ncycles=1, offset=0.0,
             sense_resistance=1e3,
             awg_channel=1,
             drive_channel=1, sense_channel=2,
             vdiv_drive=None, vdiv_sense=0.05,
             record_length=10000, num_averages=1,
             repeat_rate=None,
             save_directory=None, save_data=True, save_plot=False,
             auto_start=False, verbose=False,
             extra_metadata=None):
    """
    Capture a hysteresis loop using the OWON AWG and TDS6604 oscilloscope.

    Parameters
    ----------
    amplitude       : float — peak voltage of the triangle wave (V)
    period          : float — period of the triangle wave (s)
    ncycles         : int   — number of full cycles to capture
    offset          : float — DC offset of the drive waveform (V)
    sense_resistance: float — sense resistor value in ohms (for metadata)
    awg_channel     : int   — OWON output channel (1 or 2)
    drive_channel   : int   — scope channel measuring the drive voltage
    sense_channel   : int   — scope channel measuring sense resistor voltage
    vdiv_drive      : float — scope V/div for drive channel (auto if None)
    vdiv_sense      : float — scope V/div for sense channel
    record_length   : int   — scope record length in samples
    num_averages    : int   — number of waveforms to average
    repeat_rate     : float — AWG burst repeat period (s); default 2*ncycles*period
    save_directory  : str   — directory to save CSV files
    save_data       : bool  — whether to save data to CSV
    save_plot       : bool  — whether to save a quick waveform plot
    auto_start      : bool  — if False, prompts before enabling AWG output
    verbose         : bool  — print progress
    extra_metadata  : dict  — additional key/value pairs written to the CSV header

    Returns
    -------
    dict with keys 'drive' and 'sense', each a waveform dict with
    'time' (s), 'voltage' (V), and 'metadata'.
    """
    awg = OWONAG3062(OWONAG3062.VISA_ADDRESS)
    scope = TDS6604('GPIB0::2::INSTR')

    if verbose:
        print(f"Connected AWG:   {awg.identify()}")
        print(f"Connected scope: {scope.id}")

    try:
        # 1. Configure AWG (output stays OFF)
        setup_awg_hyst(
            awg, amplitude=amplitude, period=period, ncycles=ncycles,
            offset=offset, channel=awg_channel, repeat_rate=repeat_rate,
            verbose=verbose
        )

        # 2. Configure scope
        setup_scope_hyst(
            scope, amplitude=amplitude, period=period, ncycles=ncycles,
            drive_channel=drive_channel, sense_channel=sense_channel,
            vdiv_drive=vdiv_drive, vdiv_sense=vdiv_sense,
            record_length=record_length, num_averages=num_averages,
            verbose=verbose
        )

        # 3. Arm the scope — it now waits for the trigger
        scope.arm()
        time.sleep(0.2)

        if not auto_start:
            input("Scope armed. Press Enter to enable AWG output...")

        # 4. Enable AWG: burst_state on first, then output — timer fires immediately
        ch = awg.ch1 if awg_channel == 1 else awg.ch2
        ch.burst_state = True
        ch.output_state = True

        if verbose:
            print("AWG running — waiting for scope to trigger...")

        # 5. Wait for the scope to capture (one full burst + margin)
        if repeat_rate is None:
            repeat_rate_s = 2 * ncycles * period
        else:
            repeat_rate_s = repeat_rate

        timeout = repeat_rate_s + ncycles * period + 2.0

        if not scope.wait_for_trigger(timeout=timeout):
            raise TimeoutError(
                f"Scope did not trigger within {timeout:.1f} s. "
                "Check AWG output and trigger level."
            )

        # 6. Read waveforms
        drive_data = getattr(scope, f'ch{drive_channel}').get_waveform()
        sense_data = getattr(scope, f'ch{sense_channel}').get_waveform()

        # 7. Turn AWG off
        ch.burst_state = False
        ch.output_state = False

        if verbose:
            n_pts = len(drive_data['voltage'])
            print(f"Captured {n_pts} points per channel.")

        # 8. Build metadata
        metadata = {
            'amplitude_V': amplitude,
            'period_s': period,
            'ncycles': ncycles,
            'offset_V': offset,
            'sense_resistance_ohm': sense_resistance,
            'awg_channel': awg_channel,
            'drive_scope_channel': drive_channel,
            'sense_scope_channel': sense_channel,
            'record_length': record_length,
            'num_averages': num_averages,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        # 9. Save
        if save_data and save_directory is not None:
            amp_str = f"{amplitude:.2f}V".replace('.', 'p')
            per_str = f"{period*1e6:.1f}us".replace('.', 'p')
            base = f"hyst_{amp_str}_{per_str}"

            save_waveform(
                drive_data,
                filename=f"{base}_drive",
                directory=save_directory,
                format='csv',
                metadata={**metadata, 'channel': 'drive'},
                overwrite=False,
                verbose=verbose
            )
            save_waveform(
                sense_data,
                filename=f"{base}_sense",
                directory=save_directory,
                format='csv',
                metadata={**metadata, 'channel': 'sense'},
                overwrite=False,
                verbose=verbose
            )

        return {'drive': drive_data, 'sense': sense_data}

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
