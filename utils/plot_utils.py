from pathlib import Path
import warnings

warnings.filterwarnings('ignore', message='The palette list has more values')
import matplotlib.pyplot as plt
from pathlib import Path
import seaborn as sns
from utils.proc_utils import *

twocolors = ['#0000a2', '#bc272d']
fourcolors = ['#0000a2', '#bc272d', '#50ad9f', '#e9c716']
eightcolors = ['#003a7d','#008dff','#ff73b6','#c701ff','#4ecb8d','#ff9d3a','#f9e858','#d83034']

# ============================================================
# PLOTTING FUNCTIONS
# ============================================================

def plot_shmoo(df, save_path=None, ax=None):
    """Shmoo: dP vs nd_amplitude with tanh fit"""
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)

    sns.scatterplot(data=df, x='nd_amplitude', y='dP_uC_cm2',
                    s=30, palette=twocolors, hue='polarity', ax=ax)
    try:
        result = fit_tanh(df['nd_amplitude'], abs(df['dP_uC_cm2']))
        cent = result['center']
        ax.text(0.3, 0.0 * np.max(result['fit_curve']), rf'Vc:{cent:.3f}')
        half = int(len(df['nd_amplitude']) / 2)
        ax.plot(df['nd_amplitude'][:half], result['fit_curve'][:half], 'k--', lw=0.5)
    except Exception as e:
        print(f"  Tanh fit failed: {e}")

    ax.set_xlabel('V')
    ax.set_ylabel('dP')
    ax.set_title('Shmoo')
    ax.set_facecolor('white')

    if standalone:
        fig.tight_layout()
        if save_path:
            fig.savefig(save_path)
        plt.show()
        plt.close()


def plot_squint(df, save_path=None, ax=None):
    """Squint: dP vs offset"""
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)

    sns.scatterplot(x=df['base_offset'], y=abs(df['dP_uC_cm2']),
                    s=30, c=twocolors[0], ax=ax)
    try:
        result = fit_gaussian(df['base_offset'], abs(df['dP_uC_cm2']))
        cent = result['center']
        ax.text(0, np.max(result['fit_curve']), rf'Center:{cent:.3f}')
        ax.plot(df['base_offset'], result['fit_curve'], color='k', lw=0.5)
    except Exception as e:
        print(f"  Gaussian fit failed: {e}")

    ax.set_xlabel('Offset (V)')
    ax.set_ylabel('dP')
    ax.set_title('Squint')
    ax.set_facecolor('white')

    if standalone:
        fig.tight_layout()
        if save_path:
            fig.savefig(save_path)
        plt.show()
        plt.close()


def plot_fatigue(df, save_path=None, ax=None):
    """Fatigue: dP vs cycle_count with leakage on second y-axis"""
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(1, 1, figsize=(2.3, 2), dpi=200)
    else:
        fig = ax.get_figure()

    fatigue_voltage = df['fatigue_amplitude'].iloc[0]
    # Primary axis: dP
    sns.scatterplot(x=df['cycle_count'], y=df['dP_uC_cm2'],
                    s=30, c=twocolors[0], ax=ax)
    ax.set_xscale('log')
    ax.set_xlabel('Cycle Count')
    ax.set_ylabel('dP (µC/cm²)', color=twocolors[0])
    ax.tick_params(axis='y', labelcolor=twocolors[0])

    # Secondary axis: leakage current
    ax2 = ax.twinx()
    # Apply all rcParams from style file to ax2
    ax2.tick_params(labelsize=plt.rcParams['ytick.labelsize'])
    ax2.yaxis.label.set_size(plt.rcParams['axes.labelsize'])
    for spine in ax2.spines.values():
        spine.set_linewidth(plt.rcParams['axes.linewidth'])

    sns.scatterplot(x=df['cycle_count'], y=df['leakage_current_uA'],
                    s=10, c=twocolors[1], ax=ax2, zorder=0)
    ax2.set_ylabel('I (µA)', color=twocolors[1])
    ax2.tick_params(axis='y', labelcolor=twocolors[1])

    ax.set_title(f'{fatigue_voltage}V Fatigue')
    ax.set_facecolor('white')

    if standalone:
        fig.tight_layout()
        if save_path:
            fig.savefig(save_path)
        plt.show()
        plt.close()


def plot_ret(df, save_path=None, ax=None):
    """Retention (UDUU): dP vs elapsed_time_s"""
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)

    ret_voltage = df['pulse_amplitude'].iloc[0]

    sns.scatterplot(data=df, x=df['d_to_u_delay_s'], y='dP_uC_cm2',
                    s=30, c=twocolors[0], ax=ax)
    ax.set_xscale('log')

    try:
        result = fit_power_law(df['d_to_u_delay_s'], abs(df['dP_uC_cm2']))
        half = int(len(df['d_to_u_delay_s']) / 2)
        ax.plot(df['d_to_u_delay_s'][:half], result['fit_curve'][:half], 'k--', lw=0.5)
        ax.plot(df['d_to_u_delay_s'][:half], -result['fit_curve'][:half], 'k--', lw=0.5)
    except Exception as e:
        print(f"  Powerlaw fit failed: {e}")

    ax.set_xlabel('Delay (s)')
    ax.set_ylabel('Pr')
    ax.set_title(f'{ret_voltage}V Retention')
    ax.set_facecolor('white')

    if standalone:
        fig.tight_layout()
        if save_path:
            fig.savefig(save_path)
        plt.show()
        plt.close()


# Map measurement type to (pattern, plot_function)
MEASUREMENT_CONFIG = {
    'shmoo': ('3pp_*.csv', plot_shmoo),
    'squint': ('3pp_*.csv', plot_squint),
    'fatigue': ('3pp_*.csv', plot_fatigue),
    'ret': ('uduu_*.csv', plot_ret),
}


def process_sample(sample_directory, cd_um, measurement_config=MEASUREMENT_CONFIG,
                   shepherd_data=r"C:\Users\petermeisenheimer\Shepherd\data"):
    base_path = Path(shepherd_data) / sample_directory
    sample_name = Path(sample_directory).parts[0]

    print(f"\nScanning: {base_path}")
    print("=" * 60)

    # Find all subdirectories matching measurement types
    found_dirs = {}
    for meas_type in measurement_config.keys():
        matches = sorted([d for d in base_path.iterdir()
                          if d.is_dir() and meas_type in d.name.lower()])
        if matches:
            found_dirs[meas_type] = matches

    if not found_dirs:
        print("No matching subdirectories found!")
        return {}

    print(f"Found directories:")
    for meas_type, dirs in found_dirs.items():
        for d in dirs:
            print(f"  [{meas_type}] {d.name}")
    print()

    # Process each directory
    all_results = {}

    for meas_type, dirs in found_dirs.items():
        pattern, plot_func = measurement_config[meas_type]

        for subdir in dirs:
            print(f"\n{'=' * 60}")
            print(f"Processing [{meas_type}]: {subdir.name}")
            print(f"{'=' * 60}")

            try:
                df = batch_analyze(
                    directory=str(subdir),
                    save_csv=True,
                    cd_um=cd_um,
                    pattern=pattern,
                )

                if df is None or df.empty:
                    print(f"  No data found in {subdir.name}, skipping...")
                    continue

                print(f"  Loaded {len(df)} measurements")

                # Save individual standalone plot
                save_path = base_path / f"{subdir.name}_plot.png"
                plot_func(df, save_path=save_path)  # ax=None → standalone
                print(f"  Plot saved: {save_path.name}")

                all_results[subdir.name] = df

            except Exception as e:
                print(f"  Error processing {subdir.name}: {e}")
                continue

    # ================================================================
    # SUMMARY PLOT: 1x4 subplots
    # ================================================================
    subplot_order = ['squint', 'shmoo', 'fatigue', 'ret']

    fig, axes = plt.subplots(1, 4, figsize=(8, 2), dpi=200,
                             gridspec_kw={'wspace': 0.4})
    fig.suptitle(sample_name, fontsize=8, fontweight='bold')

    for ax, meas_type in zip(axes, subplot_order):
        ax.set_facecolor('white')

        matching = {k: v for k, v in all_results.items()
                    if meas_type in k.lower()}

        if not matching:
            ax.text(0.5, 0.5, 'No data', transform=ax.transAxes,
                    ha='center', va='center', fontsize=6, color='gray')
            ax.set_xticks([])
            ax.set_yticks([])
            continue

        try:
            df = list(matching.values())[-1]
            pattern, plot_func = measurement_config[meas_type]

            # Pass ax directly - reuses the exact same plotting logic
            plot_func(df, save_path=None, ax=ax)

        except Exception as e:
            ax.text(0.5, 0.5, f'Error:\n{str(e)[:20]}',
                    transform=ax.transAxes,
                    ha='center', va='center', fontsize=5, color='red')

    # fig.tight_layout()
    summary_path = base_path / f"{sample_name}_summary.png"
    fig.savefig(summary_path, bbox_inches='tight')
    print(f"\nSummary plot saved: {summary_path}")
    plt.show()
    plt.close()

    return all_results


def metaplot(files, normalize=False, label_list=None, doubleshmoo=False):
    # Determine flag from any file containing the keyword
    flag_map = {'shmoo': 'shmoo', 'squint': 'squint', 'ret': 'ret', 'fatigue': 'fatigue'}
    flag = next((v for k, v in flag_map.items() if k in files[0]), None)
    if flag is None:
        raise ValueError(f"Could not determine measurement type from: {files[0]}")
    print(f"Found {flag}")

    normflag = 'norm' if normalize else ''
    fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)
    save_path = None

    # Load all files and add path metadata at once
    dfs = []
    for fn in files:
        fn = Path(fn)
        df = pd.read_csv(fn)
        parts = fn.parts
        data_idx = parts.index('data')

        if save_path is None:
            save_path = Path(*parts[:data_idx + 2]) / f'combined_{flag}_{normflag}.png'

        df['sample'] = parts[data_idx + 1]
        df['device'] = parts[data_idx + 2]
        df['cd'] = parts[data_idx + 3]
        df['meas_type'] = parts[data_idx + 4]
        dfs.append(df)

    # Set axis labels/title once outside the loop
    axis_config = {
        'shmoo': ('V', 'dP', 'shmoo'),
        'squint': ('offset V', 'dP', 'squint'),
        'ret': ('Time (s)', '2Pr', 'retention'),
    }
    xlabel, ylabel, title = axis_config.get(flag, ('', '', flag))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(('normalized ' if normalize else '') + title)
    if flag == 'ret':
        ax.set_xscale('log')

    for n, df in enumerate(dfs):
        label = df['sample'].iloc[0] if not label_list else label_list[n]
        color = eightcolors[n]
        plot_kwargs = dict(ms=2.5, marker='o', c=color, label=label, ax=ax)

        if flag == 'shmoo':
            posdf = df[df['polarity'] == 'npp']
            y = posdf['dP_uC_cm2'] / (posdf['dP_uC_cm2'].iloc[-1] if normalize else 1)
            sns.lineplot(data=posdf, x='nd_amplitude', y=y, **plot_kwargs)

            if doubleshmoo:
                negdf = df[df['polarity'] == 'pnn']
                y = negdf['dP_uC_cm2'] / (negdf['dP_uC_cm2'].iloc[-1] if normalize else 1)
                plot_kwargs['label'] = None
                sns.lineplot(data=negdf, x='nd_amplitude', y=y, **plot_kwargs)

        elif flag == 'squint':
            y = abs(df['dP_uC_cm2']) / (df['dP_uC_cm2'].abs().max() if normalize else 1)
            sns.lineplot(x=df['base_offset'], y=y, **plot_kwargs)

        elif flag == 'ret':
            df_pp = df[df['polarity'] == 'pp'].reset_index(drop=True)
            df_nn = df[df['polarity'] == 'nn'].reset_index(drop=True)
            min_len = min(len(df_pp), len(df_nn))
            time_s = df_pp['d_to_u_delay_s'].values[:min_len]
            dP_diff = (df_pp['dP_uC_cm2'].values[:min_len] -
                       df_nn['dP_uC_cm2'].values[:min_len])
            y = dP_diff / (dP_diff[-1] if normalize else 1)
            sns.lineplot(x=time_s, y=y, **plot_kwargs)

    ax.set_facecolor('white')
    fig.tight_layout()
    fig.savefig(save_path)
    print(f"Saved: {save_path}")
    plt.show()
    plt.close()


def load_traces(data_list=None, directory=None, pattern='3pp_*.csv',
                polarity_filter=None, sort_by_polarity=False):
    """
    Load voltage traces from files into a DataFrame with all metadata as columns

    Args:
        data_list: List of waveform dicts or file paths (overrides directory)
        directory: Path to a specific measurement directory
        pattern: Glob pattern for files in directory
        polarity_filter: Filter by polarity ('npp', 'pnn', or None for all)
        sort_by_polarity: If True, sort by polarity

    Returns:
        DataFrame with columns: time_ns, voltage_V, label, filename, + all metadata keys
    """
    # Load files from directory if no data_list provided
    if data_list is None and directory is not None:
        directory = Path(directory)
        files = sorted(directory.glob(pattern))

        if polarity_filter:
            files = [f for f in files if polarity_filter in f.name]

        data_list = [str(f) for f in files]

        if not data_list:
            print(f"No files found matching {pattern} in {directory}")
            return None

    all_dfs = []

    for data in data_list:
        if isinstance(data, (str, Path)):
            d = load_data(str(data))  # [8]
            time_ns = d['time_ns']
            voltage = d['voltage_V']
            metadata = d['metadata']
            label = Path(data).stem
            filename = str(data)
            print(filename)
        else:
            time_ns = data['time'] * 1e9
            voltage = data['voltage']
            metadata = {}
            label = ''
            filename = ''

        # Build per-file DataFrame
        df = pd.DataFrame({
            'time_ns': time_ns,
            'voltage_V': voltage,
            'label': label,
            'filename': filename,
        })

        # Add all metadata as columns - same value repeated for every row
        for key, val in metadata.items():
            try:
                df[key] = float(val)
            except (ValueError, TypeError):
                df[key] = val

        all_dfs.append(df)

    if not all_dfs:
        return None

    result = pd.concat(all_dfs, ignore_index=True)

    if sort_by_polarity and 'polarity' in result.columns:
        result = result.sort_values('polarity').reset_index(drop=True)

    return result


def plot_peak_traces(directory, pattern='3pp_*.csv', polarity_filter='npp',
                     sort_by_polarity=True, peak='n', offset=True,
                     hue='nd_amplitude', palette='managua', offset_scale_factor=2,
                     downsample=10, save_path=None):
    directory = Path(directory)

    # Load traces - UNCHANGED from original
    df = load_traces(
        directory=str(directory),
        pattern=pattern,
        polarity_filter=polarity_filter,
        sort_by_polarity=sort_by_polarity
    )

    # Calculate peak windows from metadata
    pulse_width_ns = df['pulse_width_ns'].iloc[0]
    u_to_n_delay = df['u_to_n_delay'].iloc[0]
    n_to_d_delay = df['n_to_d_delay'].iloc[0]
    pre_pulse_delay_ns = df['pre_pulse_delay_ns'].iloc[0] if 'pre_pulse_delay_ns' in df.columns else 0

    u_start = pre_pulse_delay_ns
    n_start = u_start + pulse_width_ns + u_to_n_delay
    d_start = n_start + pulse_width_ns + n_to_d_delay

    peak_windows = {
        'u': (u_start, u_start + pulse_width_ns + 0.8*u_to_n_delay),
        'n': (n_start-0.2*u_to_n_delay, n_start + pulse_width_ns + 0.8*n_to_d_delay),
        'd': (d_start-0.2*n_to_d_delay, d_start + pulse_width_ns + 0.8*n_to_d_delay),
    }
    start_ns, end_ns = peak_windows[peak]

    # EVERYTHING BELOW IS UNCHANGED from original snippet
    df = df.loc[(df.time_ns > start_ns) & (df.time_ns < end_ns)]

    if offset:
        amplitudes = sorted(df[hue].unique())
        offset_scale = df['voltage_V'].std() * offset_scale_factor
        offset_map = {amp: i * offset_scale for i, amp in enumerate(amplitudes)}
        df['voltage_plot'] = df['voltage_V'] + df[hue].map(offset_map)
    else:
        df['voltage_plot'] = df['voltage_V']

    fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)
    ax.set_facecolor('w')
    m = sns.lineplot(data=df[::downsample], x='time_ns', y='voltage_plot',
                     palette=palette, hue=hue)
    ax.legend(fontsize=6, title='pulse V', title_fontsize=6)

    if save_path is None:
        save_path = directory / f'traces_{peak}_{polarity_filter}.png'
    fig.savefig(save_path)
    plt.show()
    plt.close()

    return df


def plot_nd_traces(directory, pattern='3pp_*.csv', polarity_filter='npp',
                   downsample=10, palette='managua', save_path=None):

    directory = Path(directory)

    df = load_traces(
        directory=str(directory),
        pattern=pattern,
        polarity_filter=polarity_filter,
    )

    pulse_width_ns     = df['pulse_width_ns'].iloc[0]
    u_to_n_delay       = df['u_to_n_delay'].iloc[0]
    n_to_d_delay       = df['n_to_d_delay'].iloc[0]
    pre_pulse_delay_ns = df['pre_pulse_delay_ns'].iloc[0] if 'pre_pulse_delay_ns' in df.columns else 0

    u_start = pre_pulse_delay_ns
    n_start = u_start + pulse_width_ns + u_to_n_delay
    d_start = n_start + pulse_width_ns + n_to_d_delay

    peak_windows = {
        'u': (u_start,                        u_start + pulse_width_ns + 0.8*u_to_n_delay),
        'n': (n_start - 0.2*n_to_d_delay,     n_start + pulse_width_ns + 0.8*n_to_d_delay),
        'd': (d_start - 0.2*n_to_d_delay,     d_start + pulse_width_ns + 0.8*n_to_d_delay),
    }

    # Filter to highest voltage only
    max_voltage = df['nd_amplitude'].max()
    df = df[df['nd_amplitude'] == max_voltage].copy()

    df_n = df.loc[(df.time_ns > peak_windows['n'][0]) & (df.time_ns < peak_windows['n'][1])].copy()
    df_d = df.loc[(df.time_ns > peak_windows['d'][0]) & (df.time_ns < peak_windows['d'][1])].copy()

    df_n['time_plot'] = df_n['time_ns'] - n_start
    df_d['time_plot'] = df_d['time_ns'] - d_start

    df_n['peak'] = 'N'
    df_d['peak'] = 'D'

    combined = pd.concat([df_n, df_d], ignore_index=True)

    fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)
    ax.set_facecolor('w')
    sns.lineplot(data=combined[::downsample], x='time_plot', y='voltage_V',
                 hue='peak', palette=palette, ax=ax)
    ax.legend(fontsize=6, title='peak', title_fontsize=6)
    ax.set_xlabel('Time from rising edge (ns)')
    ax.set_ylabel('Voltage (V)')
    ax.set_title(f'N vs D | {polarity_filter} | {max_voltage}V')

    if save_path is None:
        save_path = directory / f'nd_traces_{polarity_filter}.png'
    fig.savefig(save_path)
    plt.show()
    plt.close()

    return combined