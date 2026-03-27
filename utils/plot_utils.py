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


def metaplot(files, normalize=False):
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
        label = df['sample'].iloc[0]
        color = eightcolors[n]
        plot_kwargs = dict(ms=2.5, marker='o', c=color, label=label, ax=ax)

        if flag == 'shmoo':
            posdf = df[df['polarity'] == 'npp']
            y = posdf['dP_uC_cm2'] / (posdf['dP_uC_cm2'].iloc[-1] if normalize else 1)
            sns.lineplot(data=posdf, x='nd_amplitude', y=y, **plot_kwargs)

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
