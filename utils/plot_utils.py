from pathlib import Path
import warnings
warnings.filterwarnings('ignore', message='The palette list has more values')
import matplotlib.pyplot as plt
import seaborn as sns
from utils.proc_utils import *

twocolors = ['#0000a2','#bc272d']
fourcolors = ['#0000a2','#bc272d','#50ad9f','#e9c716']

# ============================================================
# PLOTTING FUNCTIONS
# ============================================================

def plot_shmoo(df, save_path):
    """Shmoo: dP vs nd_amplitude with tanh fit"""
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
    fig.tight_layout()
    fig.savefig(save_path)
    plt.show()
    plt.close()


def plot_squint(df, save_path):
    """Squint: dP vs offset"""
    fig, ax = plt.subplots(1,1, figsize = (2,2), dpi=200)
    sns.scatterplot(x=df['base_offset'], y=abs(df['dP_uC_cm2']), s=30, c=twocolors[0])
    try:
        result = fit_gaussian(df['base_offset'], abs(df['dP_uC_cm2']))
        cent = result['center']
        ax.text(0,np.max(result['fit_curve']),rf'Center:{cent:.3f}')
        ax.plot(df['base_offset'],result['fit_curve'], color='k', lw=0.5)
    except Exception as e:
        print(f"  Gaussian fit failed: {e}")

    ax.set_xlabel('Offset (V)')
    ax.set_ylabel('dP')
    ax.set_title('Squint')
    ax.set_facecolor('white')
    fig.tight_layout()
    fig.savefig(save_path)
    plt.show()
    plt.close()


def plot_fatigue(df, save_path):
    """Fatigue: dP vs cycle_count with leakage on second y-axis"""
    fig, ax1 = plt.subplots(1, 1, figsize=(2.3, 2), dpi=200)

    # Primary axis: dP
    sns.scatterplot(x=df['cycle_count'], y=df['dP_uC_cm2'],
                    s=30, c=twocolors[0], ax=ax1)
    ax1.set_xscale('log')
    ax1.set_xlabel('Cycle Count')
    ax1.set_ylabel('dP (µC/cm²)', color=twocolors[0])
    ax1.tick_params(axis='y', labelcolor=twocolors[0])

    # Secondary axis: leakage current
    ax2 = ax1.twinx()
    sns.scatterplot(x=df['cycle_count'], y=df['leakage_current_uA'],
                    s=10, c=twocolors[1], ax=ax2, zorder=0)
    ax2.set_ylabel('I (µA)', color=twocolors[1])
    ax2.tick_params(axis='y', labelcolor=twocolors[1])

    ax1.set_title('Fatigue')
    ax1.set_facecolor('white')
    fig.tight_layout()
    fig.savefig(save_path)
    plt.show()
    plt.close()


def plot_ret(df, save_path):
    """Retention (UDUU): dP vs elapsed_time_s"""
    fig, ax = plt.subplots(1, 1, figsize=(2, 2), dpi=200)
    sns.scatterplot(data=df, x=df['d_to_u_delay_s'], y='dP_uC_cm2', s=30, c=twocolors[0])
    ax.set_xscale('log')

    try:
        result = fit_power_law(df['d_to_u_delay_s'], abs(df['dP_uC_cm2']))
        # ax.text(0.5,0.0*np.max(result['fit_curve']),rf'Vc:{cent:.3f}')
        half = int(len(df['d_to_u_delay_s'])/2)
        ax.plot(df['d_to_u_delay_s'][:half],
                result['fit_curve'][:half],
                'k--', lw=0.5)

        ax.plot(df['d_to_u_delay_s'][:half],
                -result['fit_curve'][:half],
                'k--', lw=0.5)
    except Exception as e:
        print(f"  Powerlaw fit failed: {e}")

    ax.set_xscale('log')
    ax.set_xlabel('Delay (s)')
    ax.set_ylabel('Pr')
    ax.set_title('Retention')
    ax.set_facecolor('white')
    fig.tight_layout()
    fig.savefig(save_path)
    plt.show()
    plt.close()


# Map measurement type to (pattern, pulsetrain, plot_function)
MEASUREMENT_CONFIG = {
    'shmoo':   ('3pp_*.csv',  plot_shmoo),
    'squint':  ('3pp_*.csv',  plot_squint),
    'fatigue': ('3pp_*.csv',  plot_fatigue),
    'ret':     ('uduu_*.csv',  plot_ret),
}

def process_sample(sample_directory, cd_um, measurement_config = MEASUREMENT_CONFIG,
                   shepherd_data=r"C:\Users\petermeisenheimer\Shepherd\data"):
    """
    Process all measurement subdirectories for a given sample

    Args:
        sample_directory: Relative path to sample directory (e.g. 'SP024\\A6-cd10')
        cd_um: Contact diameter in microns
        measurement_config: Dict mapping measurement type to (pattern, plot_func)
        shepherd_data: Base data directory path

    Returns:
        dict: {subdir_name: DataFrame} for all successfully processed directories
    """
    base_path = Path(shepherd_data) / sample_directory

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

                # Save plot to top-level sample directory
                save_path = base_path / f"{subdir.name}_plot.png"
                plot_func(df, save_path)
                print(f"  Plot saved: {save_path.name}")

                all_results[subdir.name] = df

            except Exception as e:
                print(f"  Error processing {subdir.name}: {e}")
                continue

    print(f"\n{'=' * 60}")
    print("Processing complete!")
    print(f"  Processed {len(all_results)}/{sum(len(d) for d in found_dirs.values())} directories")
    print(f"{'=' * 60}")

    return all_results