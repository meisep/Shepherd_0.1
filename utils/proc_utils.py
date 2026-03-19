import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from scipy.optimize import curve_fit
import glob
from pathlib import Path

def load_data(filepath):
    """Load trace data from CSV"""
    data = pd.read_csv(filepath, comment='#')
    metadata = {}
    with open(filepath, 'r') as f:
        for line in f:
            if line.startswith('#') and ':' in line:
                key, val = line[1:].strip().split(':', 1)
                metadata[key.strip()] = val.strip()
    return {
        'time_ns': data['time_ns'].values,
        'voltage_V': data['voltage_V'].values,
        'metadata': metadata
    }

def find_3pp_peaks(voltage_V, prominence_factor=0.2):
    """Find all peaks in the waveform (3 for '3pp', 2 for 'uduu')"""
    peaks, properties = signal.find_peaks(
        voltage_V,
        prominence=prominence_factor * np.max(voltage_V),
        distance=50
    )
    if len(peaks) < 3:
        raise ValueError(f"Expected 3 peaks, found {len(peaks)}")
    if len(peaks) > 3:
        largest = np.argsort(properties['prominences'])[-3:]
        peaks = np.sort(peaks[largest])
    return peaks

def find_uduu_peaks(voltage_V, prominence_factor=0.2):
    """Find all peaks in the waveform (3 for '3pp', 2 for 'uduu')"""
    peaks, properties = signal.find_peaks(
        voltage_V,
        prominence=prominence_factor * np.max(voltage_V),
        distance=50
    )
    if len(peaks) < 2:
        raise ValueError(f"Expected 3 peaks, found {len(peaks)}")
    if len(peaks) > 2:
        largest = np.argsort(properties['prominences'])[-3:]
        peaks = np.sort(peaks[largest])
    return peaks

def find_rising_edge_before_peak(voltage_V, peak_idx, search_back_ns=20, dt_ns=0.1):
    """Find where rising edge starts before peak"""
    search_samples = int(search_back_ns / dt_ns)
    start_idx = max(0, peak_idx - search_samples)
    threshold = 0.05 * abs(voltage_V[peak_idx])
    for i in range(peak_idx, start_idx, -1):
        if abs(voltage_V[i]) < threshold:
            return i + 1
    return start_idx

def align_peaks_3pp(time_ns, voltage_V, metadata, truncate_factor=0.95):
    """Align N and D peaks at their rising edges"""
    pulse_width = float(metadata.get('pulse_width_ns', 200))
    polarity = metadata.get('polarity', 'npp')

    if polarity == 'pnn' or polarity == 'nn':
        voltage_V = -voltage_V
    else:  # npp
        voltage_V = voltage_V

    peaks = find_3pp_peaks(voltage_V)
    dt_ns = np.mean(np.diff(time_ns))


    n_edge_idx = find_rising_edge_before_peak(voltage_V, peaks[1], dt_ns=dt_ns)
    d_edge_idx = find_rising_edge_before_peak(voltage_V, peaks[2], dt_ns=dt_ns)

    window_samples = int(truncate_factor * pulse_width / dt_ns)
    n_end = min(len(time_ns), n_edge_idx + window_samples)
    d_end = min(len(time_ns), d_edge_idx + window_samples)

    return {
        'n_time': time_ns[n_edge_idx:n_end] - time_ns[n_edge_idx],
        'n_voltage': voltage_V[n_edge_idx:n_end],
        'd_time': time_ns[d_edge_idx:d_end] - time_ns[d_edge_idx],
        'd_voltage': voltage_V[d_edge_idx:d_end]
    }

def align_peaks_uduu(time_ns, voltage_V, metadata, truncate_factor=0.95):
    """Align N and D peaks at their rising edges"""
    pulse_width = float(metadata.get('pulse_width_ns', 200))
    polarity = metadata.get('polarity', 'npp')

    if polarity == 'pnn' or polarity == 'nn':
        voltage_V = -voltage_V
    else:  # npp
        voltage_V = voltage_V

    peaks = find_uduu_peaks(voltage_V)
    dt_ns = np.mean(np.diff(time_ns))


    n_edge_idx = find_rising_edge_before_peak(voltage_V, peaks[0], dt_ns=dt_ns)
    d_edge_idx = find_rising_edge_before_peak(voltage_V, peaks[1], dt_ns=dt_ns)

    window_samples = int(truncate_factor * pulse_width / dt_ns)
    n_end = min(len(time_ns), n_edge_idx + window_samples)
    d_end = min(len(time_ns), d_edge_idx + window_samples)

    return {
        'n_time': time_ns[n_edge_idx:n_end] - time_ns[n_edge_idx],
        'n_voltage': voltage_V[n_edge_idx:n_end],
        'd_time': time_ns[d_edge_idx:d_end] - time_ns[d_edge_idx],
        'd_voltage': voltage_V[d_edge_idx:d_end]
    }

def calculate_polarization(aligned_data, metadata, resistance=50, cd_um=np.nan):
    """
    Calculate P* (N), P^ (D), and dP (difference)
    Returns dictionary suitable for DataFrame construction
    """
    # Interpolate D onto N's time base
    common_time = aligned_data['n_time']
    d_interp = np.interp(common_time, aligned_data['d_time'], aligned_data['d_voltage'])

    # Calculate individual charges
    time_s = common_time * 1e-9

    # N charge (P*)
    current_n = aligned_data['n_voltage'] / resistance
    charge_n_C = np.trapezoid(current_n, time_s)
    if metadata.get('polarity', 'npp') == 'pnn' or metadata.get('polarity', 'npp') == 'nn':
        charge_n_C = -charge_n_C

    # D charge (P^)
    current_d = d_interp / resistance
    charge_d_C = np.trapezoid(current_d, time_s)
    if metadata.get('polarity', 'npp') == 'pnn' or metadata.get('polarity', 'npp') == 'nn':
        charge_d_C = -charge_d_C

    if 'n_voltage' in aligned_data and aligned_data['n_voltage'] is not None:
        u_voltage_end = aligned_data['n_voltage'][-5:]
        leakage_voltage = np.mean(u_voltage_end)
        leakage_current_A = leakage_voltage / resistance
        leakage_current_uA = leakage_current_A * 1e6

        if metadata.get('polarity', 'npp') in ['pnn', 'nn']:
            leakage_current_uA = -leakage_current_uA
    else:
        leakage_voltage = np.nan
        leakage_current_uA = np.nan

    # Get device area
    area_cm2 = float(metadata.get('device_area_cm2', 'nan'))
    if not np.isnan(cd_um):
        area_cm2 = np.pi * (cd_um / 2 * 1e-4) ** 2

    # Build results dictionary
    results = {
        # Metadata
        'polarity': metadata.get('polarity', ''),
        'base_offset': float(metadata.get('base_offset', np.nan)),
        'pulse_width_ns': float(metadata.get('pulse_width_ns', np.nan)),
        'capture_width_ns': float(metadata.get('capture_width_ns', np.nan)),
        'record_length': int(metadata.get('record_length', 0)),
        'num_averages': int(metadata.get('num_averages', 1)),
        'cd_um': cd_um,
        'device_area_cm2': area_cm2,

        'u_amplitude': float(metadata.get('u_amplitude', np.nan)),
        'u_to_n_delay': float(metadata.get('u_to_n_delay', np.nan)),
        'nd_amplitude': float(metadata.get('nd_amplitude', np.nan)),
        'n_to_d_delay': float(metadata.get('n_to_d_delay', np.nan)),

        'pulse_amplitude': float(metadata.get('pulse_amplitude', np.nan)),
        'u_to_d_delay': float(metadata.get('u_to_d_delay', np.nan)),
        'd_to_u_delay': float(metadata.get('d_to_u_delay', np.nan)),
        'd_to_u_delay_s': float(metadata.get('d_to_u_delay_s', np.nan)),
        'u_to_u_delay': float(metadata.get('u_to_u_delay', np.nan)),

        # Charge values
        'charge_n_pC': charge_n_C * 1e12,
        'charge_d_pC': charge_d_C * 1e12,
        'charge_diff_pC': (charge_n_C - charge_d_C) * 1e12,

        # Leakage
        'leakage_voltage_V': leakage_voltage,
        'leakage_current_uA': leakage_current_uA,

        # Cycle number
        'cycle_count': float(metadata.get('cycle_count', np.nan)),
        'elapsed_time_s': float(metadata.get('elapsed_time_s', np.nan)),
        'fatigue_amplitude': float(metadata.get('fatigue_amplitude', np.nan)),
        'fatigue_frequency_hz': float(metadata.get('fatigue_frequency_hz', np.nan)),

    }

    # Calculate polarizations if area provided
    if not np.isnan(area_cm2):
        area_m2 = area_cm2 * 1e-4
        results['P_star_uC_cm2'] = (charge_n_C / area_m2) * 1e2  # P* (N)
        results['P_hat_uC_cm2'] = (charge_d_C / area_m2) * 1e2  # P^ (D)
        results['dP_uC_cm2'] = ((charge_n_C - charge_d_C) / area_m2) * 1e2  # dP
    else:
        results['P_star_uC_cm2'] = np.nan
        results['P_hat_uC_cm2'] = np.nan
        results['dP_uC_cm2'] = np.nan

    # Store waveforms for plotting
    results['_plot_data'] = {
        'time': common_time,
        'n_voltage': aligned_data['n_voltage'],
        'd_voltage': d_interp,
        'difference': aligned_data['n_voltage'] - d_interp
    }

    return results

def plot_analysis(results):
    """Plot aligned pulses and difference from results dictionary"""
    plot_data = results['_plot_data']

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

    # Overlaid pulses
    ax1.plot(plot_data['time'], plot_data['n_voltage'], 'r-', label='N pulse (P*)')
    ax1.plot(plot_data['time'], plot_data['d_voltage'], 'g-', label='D pulse (P^)')
    ax1.axhline(0, color='k', linestyle='--', alpha=0.3)
    ax1.set_xlabel('Time from rising edge (ns)')
    ax1.set_ylabel('Voltage (V)')
    ax1.set_title('Aligned N and D Pulses')
    ax1.legend()
    ax1.grid(alpha=0.3)

    # Difference
    ax2.plot(plot_data['time'], plot_data['difference'], 'b-')
    ax2.axhline(0, color='k', linestyle='--', alpha=0.3)
    ax2.fill_between(plot_data['time'], 0, plot_data['difference'], alpha=0.3)
    ax2.set_xlabel('Time from rising edge (ns)')
    ax2.set_ylabel('N - D (V)')
    ax2.grid(alpha=0.3)

    # Add results annotation
    if not np.isnan(results['P_star_uC_cm2']):
        text = (f"P* = {results['P_star_uC_cm2']:.3f} µC/cm²\n"
                f"P^ = {results['P_hat_uC_cm2']:.3f} µC/cm²\n"
                f"dP = {results['dP_uC_cm2']:.3f} µC/cm²")
    else:
        text = (f"Q(N) = {results['charge_n_pC']:.3f} pC\n"
                f"Q(D) = {results['charge_d_pC']:.3f} pC\n"
                f"dQ = {results['charge_diff_pC']:.3f} pC")

    ax2.text(0.02, 0.98, text, transform=ax2.transAxes,
             fontsize=11, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))

    plt.tight_layout()
    plt.show()

def analyze_3pp_file(filepath, cd_um=np.nan, pulsetrain='3pp'):
    """Analyze a single 3PP file and return results dictionary"""
    data = load_data(filepath)
    aligned = align_peaks_3pp(data['time_ns'], data['voltage_V'], data['metadata'])
    results = calculate_polarization(aligned, data['metadata'], cd_um=cd_um)
    results['filename'] = filepath
    results['pulsetrain'] = pulsetrain
    return results

def analyze_uduu_file(filepath, cd_um=np.nan, pulsetrain='3pp'):
    """Analyze a single UDUU file and return results dictionary"""
    data = load_data(filepath)
    aligned = align_peaks_uduu(data['time_ns'], data['voltage_V'], data['metadata'])
    results = calculate_polarization(aligned, data['metadata'], cd_um=cd_um)
    results['filename'] = filepath
    results['pulsetrain'] = pulsetrain
    return results

def batch_analyze(directory, save_csv=True, plot_all=False, cd_um=np.nan, pattern='3pp_*.csv'):
    """
    Analyze all 3PP/UDUU files in directory
    Args:
        directory: Path to directory containing CSV files
        pattern: Glob pattern for matching files (default: "3pp_*.csv")
        save_csv: If True, save results to CSV (default: True)
        plot_all: If True, plot every file (default: False, can be slow)
        cd_um: Contact diameter in microns
        pulsetrain: '3pp' for 3-pulse or 'uduu' for 2-pulse
    Returns:
        DataFrame with all results
    """

    if pattern != '3pp_*.csv' and pattern != 'uduu_*.csv':
        print(f"Invalid pattern: {pattern}")
        return None

    search_path = Path(directory) / pattern
    files = sorted(glob.glob(str(search_path)))

    if not files:
        print(f"No files found matching: {search_path}")
        return None

    results_list = []
    for i, filepath in enumerate(files, 1):
        filename = Path(filepath).name
        print(f"[{i}/{len(files)}] Processing: {filename}")

        try:
            if pattern == '3pp_*.csv':
                results = analyze_3pp_file(filepath, cd_um=cd_um)
            elif pattern == 'uduu_*.csv':
                results = analyze_uduu_file(filepath, cd_um=cd_um)

            # Remove plot data for DataFrame
            results_for_df = {k: v for k, v in results.items() if not k.startswith('_')}
            results_list.append(results_for_df)

            # Optionally plot each file
            if plot_all:
                plot_analysis(results)

            print(f"  ✓ Success - dP = {results['dP_uC_cm2']:.3f} µC/cm²")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue

    print("-" * 60)
    print(f"Successfully analyzed {len(results_list)}/{len(files)} files")

    # Create DataFrame
    if not results_list:
        print("No files were successfully analyzed")
        return None

    df = pd.DataFrame(results_list)

    # Save to CSV if requested
    if save_csv:
        if pattern == '3pp_*.csv':
            output_filename = f"3pp_analysis_results.csv"
        elif pattern == 'uduu_*.csv':
            output_filename = f"uduu_analysis_results.csv"

        output_path = Path(directory) / output_filename
        df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")

    return df

####### fits
def fit_gaussian(x_data, y_data):
    """
    Fit a Gaussian to data and return fit parameters and center point

    Args:
        x_data: x-axis data (e.g., time, position)
        y_data: y-axis data (e.g., voltage, intensity)
        plot: If True, plot the fit

    Returns:
        dict: {
            'center': center of Gaussian (mu),
            'amplitude': peak height,
            'width': standard deviation (sigma),
            'fit_curve': fitted y values,
            'params': (amplitude, center, width)
        }
    """
    # Define Gaussian function
    def gaussian(x, amplitude, center, width):
        return amplitude * np.exp(-(x - center)**2 / (2 * width**2))

    # Initial guess for parameters
    amplitude_guess = np.max(y_data) - np.min(y_data)
    center_guess = x_data[np.argmax(y_data)]
    width_guess = (np.max(x_data) - np.min(x_data)) / 4

    initial_guess = [amplitude_guess, center_guess, width_guess]

    # Fit the Gaussian
    params, covariance = curve_fit(gaussian, x_data, y_data, p0=initial_guess)
    amplitude, center, width = params

    # Generate fitted curve
    fit_curve = gaussian(x_data, amplitude, center, width)

    print(f"Gaussian Fit Results:")
    print(f"  Center (μ): {center:.6f}")
    print(f"  Amplitude: {amplitude:.6f}")
    print(f"  Width (σ): {width:.6f}")

    return {
        'center': center,
        'amplitude': amplitude,
        'width': width,
        'fit_curve': fit_curve,
        'params': params
    }

def fit_tanh(x_data, y_data, saturation_x=0.0):

    def tanh_func(x, amplitude, center, width, offset):
        return amplitude * np.tanh((x - center) / width) + offset

    y_min = np.min(y_data)
    y_max = np.max(y_data)
    amplitude_guess = (y_max - y_min) / 2
    offset_guess = (y_max + y_min) / 2

    dy = np.gradient(y_data)
    center_idx = np.argmax(np.abs(dy))
    center_guess = x_data.iloc[center_idx] if hasattr(x_data, 'iloc') else x_data[center_idx]

    width_guess = (np.max(x_data) - np.min(x_data)) / 10

    # Saturation occurs at center + 3*width
    # saturation_x - 3*width_guess
    lower_center = saturation_x + 1e-10  # Center must be above saturation_x

    center_guess = max(center_guess, lower_center)
    initial_guess = [amplitude_guess, center_guess, width_guess, offset_guess]

    bounds = (
        [-np.inf, lower_center, 1e-10, -np.inf],  # lower: center > saturation_x
        [ np.inf,      np.inf,  np.inf,  np.inf]   # upper: unconstrained
    )

    params, covariance = curve_fit(
        tanh_func,
        x_data,
        y_data,
        p0=initial_guess,
        bounds=bounds,
        method='trf',
    )

    amplitude, center, width, offset = params
    slope = amplitude / width
    fit_curve = tanh_func(x_data, amplitude, center, width, offset)
    saturation_point = center + 3 * width  # Saturation above center

    print(f"Tanh Fit Results:")
    print(f"  Center (x₀): {center:.6f}")
    print(f"  Amplitude: {amplitude:.6f}")
    print(f"  Width: {width:.6f}")
    print(f"  Slope at center: {slope:.6f}")
    print(f"  Offset: {offset:.6f}")
    print(f"  Saturation point (~99.5%): {saturation_point:.6f} (must be > {saturation_x})")

    return {
        'center': center,
        'amplitude': amplitude,
        'slope': slope,
        'width': width,
        'offset': offset,
        'fit_curve': fit_curve,
        'params': params,
        'saturation_point': saturation_point
    }

def fit_power_law(x_data, y_data):
    """
    Fit a negative power law function to data and return fit parameters

    Fits: y = amplitude * x^(-exponent) + offset

    Args:
        x_data: x-axis data (must be positive)
        y_data: y-axis data
        plot: If True, plot the fit

    Returns:
        dict: {
            'amplitude': scaling factor,
            'exponent': power law exponent (positive value),
            'offset': vertical offset,
            'fit_curve': fitted y values,
            'params': (amplitude, exponent, offset)
        }
    """
    def power_law(x, amplitude, exponent, offset):
        return amplitude * np.power(x, -exponent) + offset

    # Initial guesses
    y_min = np.min(y_data)
    y_max = np.max(y_data)
    amplitude_guess = (y_max - y_min)
    exponent_guess = 1.0  # Start with simple 1/x decay
    offset_guess = y_min

    initial_guess = [amplitude_guess, exponent_guess, offset_guess]

    # Bounds: amplitude unconstrained, exponent must be positive, offset unconstrained
    bounds = (
        [-np.inf, 1e-10, -np.inf],  # lower bounds
        [ np.inf,  np.inf,  np.inf]  # upper bounds
    )

    # Convert to numpy arrays in case of pandas Series
    x_data_np = np.array(x_data, dtype=float)
    y_data_np = np.array(y_data, dtype=float)

    # Ensure x_data is positive (required for power law)
    if np.any(x_data_np <= 0):
        raise ValueError("x_data must be strictly positive for power law fitting")

    params, covariance = curve_fit(
        power_law,
        x_data_np,
        y_data_np,
        p0=initial_guess,
        bounds=bounds,
        method='trf'
    )

    amplitude, exponent, offset = params
    perr = np.sqrt(np.diag(covariance))  # Parameter uncertainties

    fit_curve = power_law(x_data_np, amplitude, exponent, offset)

    print(f"Negative Power Law Fit Results:")
    print(f"  Amplitude: {amplitude:.6f} ± {perr[0]:.6f}")
    print(f"  Exponent:  {exponent:.6f} ± {perr[1]:.6f}")
    print(f"  Offset:    {offset:.6f} ± {perr[2]:.6f}")
    print(f"  Function:  y = {amplitude:.4f} * x^(-{exponent:.4f}) + {offset:.4f}")

    return {
        'amplitude': amplitude,
        'exponent': exponent,
        'offset': offset,
        'fit_curve': fit_curve,
        'params': params,
        'uncertainties': perr
    }