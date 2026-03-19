import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

def plot_waveform(data, filename, verbose=False):
    """Plot waveform with minimal output"""
    fig, ax = plt.subplots(1, 1, figsize=(14, 6))
    ax.plot(data['time'] * 1e9, data['voltage'], 'b-', linewidth=1)
    ax.axhline(y=0, color='k', linestyle='--', linewidth=0.5, alpha=0.3)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('Time (ns)')
    ax.set_ylabel('Voltage (V)')
    ax.set_title('3PP Measurement')
    v_max = data['voltage'].max()
    v_min = data['voltage'].min()
    margin = (v_max - v_min) * 0.1
    ax.set_ylim(v_min - margin, v_max + margin)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    if verbose:
        print(f"Saved: {filename}")
    plt.close()


def save_waveform(data, filename=None, directory=None, format='csv', metadata=None,
                  overwrite=False, verbose=False):
    """
    Save waveform data to file
    Args:
        data: Waveform dict with 'time' and 'voltage' arrays
        filename: Output filename (without extension). If None, auto-generates timestamp name
        directory: Subdirectory name within 'data' folder. If None, saves directly in 'data'.
                   Full path will be 'data/{directory}/'
        format: Save format - 'npz' (numpy), 'csv', 'txt', or 'all' #npz adn txt are disabled
        metadata: Optional dict with measurement parameters
        overwrite: If False, appends number to filename to avoid overwriting existing files
        verbose: Enable print statements
    Returns:
        str or list: Saved filename(s) with full path
    """
    # Auto-generate filename if not provided
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"3pp_{timestamp}"
    # Remove extension if provided and replace dots with 'p'
    filename = Path(filename).stem
    filename = filename.replace('.', 'p')
    # Create directory structure: data/{directory}/
    if directory is not None:
        dir_path = Path("../data") / directory
    else:
        dir_path = Path("../data")
    dir_path.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"Using directory: {dir_path}")

    # Function to get non-existing filename
    def get_unique_filename(base_path, extension):
        """Add number suffix if file exists and overwrite=False"""
        file_path = base_path.parent / f"{base_path.stem}{extension}"
        if overwrite or not file_path.exists():
            return file_path
        # Find next available number
        counter = 1
        while True:
            new_path = base_path.parent / f"{base_path.stem}_{counter:03d}{extension}"
            if not new_path.exists():
                return new_path
            counter += 1

    saved_files = []
    base_path = dir_path / filename
    if format in ['csv', 'all']:
        csv_file = get_unique_filename(base_path, '.csv')
        with open(csv_file, 'w') as f:
            if metadata:
                f.write("# 3PP Measurement Data\n")
                for key, value in metadata.items():
                    f.write(f"# {key}: {value}\n")
                f.write("#\n")
            f.write("time_ns,voltage_V\n")
            for t, v in zip(data['time'], data['voltage']):
                f.write(f"{t * 1e9:.6f},{v:.6e}\n")
        saved_files.append(str(csv_file))
        if verbose:
            print(f"Saved: {csv_file}")
    return (saved_files[0] if len(saved_files) == 1 else saved_files), dir_path