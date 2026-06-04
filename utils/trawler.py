from pathlib import Path
import pandas as pd
import numpy as np

DATA_ROOT = Path(__file__).parent.parent / 'data'

# Ordered longest-first so 'inverseshmoo' matches before 'shmoo'
_MEAS_TYPES = ['inverseshmoo', 'shmoo', 'squint', 'fatigue', 'ret', 'chirp', 'vasp', 'uduu']

# Groupby keys used when averaging each measurement type
_DEFAULT_GROUPBY = {
    'shmoo':        ('u_amplitude', 'nd_amplitude', 'polarity'),
    'inverseshmoo': ('u_amplitude', 'nd_amplitude', 'polarity'),
    'squint':       ('base_offset', 'polarity'),
    'chirp':        ('pulse_width_ns', 'polarity'),
    'fatigue':      ('cycle_count',),
    'ret':          ('d_to_u_delay_s',),
    'uduu':         ('d_to_u_delay_s',),
    'vasp':         ('u_amplitude', 'nd_amplitude', 'polarity'),
}
_FALLBACK_GROUPBY = ('u_amplitude', 'nd_amplitude', 'polarity')


def _detect_meas_type(folder_name: str) -> str:
    lower = folder_name.lower()
    for t in _MEAS_TYPES:
        if lower.startswith(t):
            return t
    return 'unknown'


def trawl(sample: str, data_root=None) -> list[dict]:
    """
    Walk a sample directory and return one record per analysis results CSV.

    The directory structure between the sample root and the measurement folder
    can have any number of levels (device, cd, run-label, etc.). All intermediate
    folder names are stored in 'subdirs' so nothing is lost.

    Each record contains:
        sample     – top-level sample folder name
        subdirs    – list of all folder names between the sample root and
                     meas_name, in order (empty list for flat samples)
        device     – subdirs[0], or None for flat samples (convenience alias)
        cd         – subdirs[-1] when len(subdirs) > 1, else None
        meas_name  – folder directly containing the results CSV
        meas_type  – normalised type prefix ('shmoo', 'ret', 'fatigue', …)
        pulsetrain – '3pp' or 'uduu'
        path       – absolute path to the analysis results CSV
    """
    root = Path(data_root) if data_root else DATA_ROOT
    sample_path = root / sample

    if not sample_path.exists():
        raise FileNotFoundError(f"Sample directory not found: {sample_path}")

    records = []
    for csv in sample_path.rglob('*_analysis_results.csv'):
        parts = csv.relative_to(sample_path).parts
        # parts[-1] = filename, parts[-2] = meas_name, parts[:-2] = subdirs
        if len(parts) < 2:
            continue

        meas_name = parts[-2]
        subdirs   = list(parts[:-2])

        device = subdirs[0]       if subdirs             else None
        cd     = subdirs[-1]      if len(subdirs) > 1    else None

        pulsetrain = '3pp' if '3pp' in csv.name else 'uduu'

        records.append({
            'sample':     sample,
            'subdirs':    subdirs,
            'device':     device,
            'cd':         cd,
            'meas_name':  meas_name,
            'meas_type':  _detect_meas_type(meas_name),
            'pulsetrain': pulsetrain,
            'path':       str(csv),
        })

    records.sort(key=lambda r: (r['subdirs'], r['meas_name']))
    return records


def filter_records(
    records: list[dict],
    device=None,
    cd=None,
    meas_type=None,
    meas_name=None,
    pulsetrain=None,
    subdirs_contain=None,
) -> list[dict]:
    """
    Filter trawl records by one or more criteria.

    device, cd, meas_type, meas_name, pulsetrain
        Each accepts a single string or a list of strings.
        Matches against the corresponding record field.

    subdirs_contain
        A single string or list of strings. Keeps only records whose
        'subdirs' list contains *all* specified values (at any position).
        Useful for filtering by any intermediate folder without knowing
        its depth, e.g. subdirs_contain='first pass' or
        subdirs_contain=['D1', 'cd10'].
    """
    def _to_set(v):
        if v is None:
            return None
        return {v} if isinstance(v, str) else set(v)

    device_set   = _to_set(device)
    cd_set       = _to_set(cd)
    type_set     = _to_set(meas_type)
    name_set     = _to_set(meas_name)
    train_set    = _to_set(pulsetrain)
    subdir_set   = _to_set(subdirs_contain)   # all of these must appear in subdirs

    out = []
    for r in records:
        if device_set  is not None and r['device']     not in device_set:  continue
        if cd_set      is not None and r['cd']         not in cd_set:      continue
        if type_set    is not None and r['meas_type']  not in type_set:    continue
        if name_set    is not None and r['meas_name']  not in name_set:    continue
        if train_set   is not None and r['pulsetrain'] not in train_set:   continue
        if subdir_set  is not None and not subdir_set.issubset(r['subdirs']): continue
        out.append(r)
    return out


def load_and_average(
    records: list[dict],
    group_by=None,
) -> pd.DataFrame | None:
    """
    Load analysis results CSVs for the given records and average numeric
    columns within each voltage/condition group.

    group_by: tuple of column names to group on. If None, uses the default
              groupby for the measurement type of the first record.

    Returns a DataFrame with mean/std per group, plus 'n_devices' showing
    how many source files contributed. Returns None if nothing loaded.
    """
    if not records:
        return None

    dfs = []
    for r in records:
        try:
            df = pd.read_csv(r['path'])
            df['_subdirs']   = str(r['subdirs'])
            df['_meas_name'] = r['meas_name']
            dfs.append(df)
        except Exception as e:
            print(f"Warning: could not load {r['path']}: {e}")

    if not dfs:
        return None

    combined = pd.concat(dfs, ignore_index=True)

    if group_by is None:
        first_type = records[0]['meas_type']
        group_by = _DEFAULT_GROUPBY.get(first_type, _FALLBACK_GROUPBY)

    valid_group = [c for c in group_by if c in combined.columns]
    if not valid_group:
        print(f"Warning: none of {group_by} found in data columns")
        return combined

    numeric_cols = [
        c for c in combined.select_dtypes(include=np.number).columns
        if c not in valid_group
    ]

    agg = combined.groupby(valid_group, dropna=False)[numeric_cols].agg(['mean', 'std', 'count'])
    agg.columns = [f'{col}_{stat}' for col, stat in agg.columns]
    agg = agg.reset_index()

    for probe in ('dP_uC_cm2_count', 'charge_diff_pC_count'):
        if probe in agg.columns:
            agg = agg.rename(columns={probe: 'n_devices'})
            break

    return agg


def load_shmoos_from_paths(dirs, polarity='both'):
    """
    Load shmoo data from a list of absolute directory paths.

    Searches each directory for subdirectories whose name starts with 'shmoo',
    loads 3pp_analysis_results.csv from each, and returns a DataFrame averaged
    across all sources grouped by (pulse_width_ns, nd_amplitude).

    polarity : 'npp'  – use only npp rows (dP already positive)
               'pnn'  – use only pnn rows, sign-flipped to positive
               'both' – average npp and sign-flipped pnn together (default)

    Returns DataFrame with columns:
        pulse_width_ns, nd_amplitude, dP_mean, dP_std, n_devices
    All dP values are positive (unsigned switching amplitude).
    """
    if polarity not in ('npp', 'pnn', 'both'):
        raise ValueError("polarity must be 'npp', 'pnn', or 'both'")

    all_dfs = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            print(f"Warning: {d} does not exist, skipping")
            continue
        shmoo_dirs = sorted([s for s in d.iterdir()
                             if s.is_dir() and s.name.lower().startswith('shmoo')])
        if not shmoo_dirs:
            print(f"No shmoo subdirectories found in {d}")
            continue
        for sd in shmoo_dirs:
            csv = sd / '3pp_analysis_results.csv'
            if not csv.exists():
                print(f"  No 3pp_analysis_results.csv in {sd.name}, skipping")
                continue
            df = pd.read_csv(csv)
            df['_source'] = str(sd)
            all_dfs.append(df)
            print(f"  Loaded {len(df)} rows from {sd.name}")

    if not all_dfs:
        return None

    combined = pd.concat(all_dfs, ignore_index=True)

    if polarity == 'npp':
        combined = combined[combined['polarity'] == 'npp'].copy()
        combined['dP_work'] = combined['dP_uC_cm2']
    elif polarity == 'pnn':
        combined = combined[combined['polarity'] == 'pnn'].copy()
        combined['dP_work'] = -combined['dP_uC_cm2']
    else:  # 'both'
        combined['dP_work'] = combined['dP_uC_cm2'].copy()
        pnn_mask = combined['polarity'] == 'pnn'
        combined.loc[pnn_mask, 'dP_work'] = -combined.loc[pnn_mask, 'dP_uC_cm2']

    grouped = (combined
               .groupby(['pulse_width_ns', 'nd_amplitude'])['dP_work']
               .agg(dP_mean='mean', dP_std='std', n_devices='count')
               .reset_index())
    return grouped


def load_chirps_from_paths(dirs, polarity='both'):
    """
    Load chirp data from a list of absolute directory paths.

    Searches each directory for subdirectories whose name starts with 'chirp',
    loads 3pp_analysis_results.csv from each, and returns a DataFrame averaged
    across all sources grouped by (u_amplitude, pulse_width_ns).

    polarity : 'npp'  – use only npp rows (dP already positive)
               'pnn'  – use only pnn rows, sign-flipped to positive
               'both' – average npp and sign-flipped pnn together (default)

    Returns DataFrame with columns:
        cd_um, pulse_width_ns, dP_mean, dP_std, n_devices
    All dP values are positive (unsigned switching amplitude).
    """
    if polarity not in ('npp', 'pnn', 'both'):
        raise ValueError("polarity must be 'npp', 'pnn', or 'both'")

    all_dfs = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            print(f"Warning: {d} does not exist, skipping")
            continue
        chirp_dirs = sorted([s for s in d.iterdir()
                             if s.is_dir() and s.name.lower().startswith('chirp')])
        if not chirp_dirs:
            print(f"No chirp subdirectories found in {d}")
            continue
        for cd in chirp_dirs:
            csv = cd / '3pp_analysis_results.csv'
            if not csv.exists():
                print(f"  No 3pp_analysis_results.csv in {cd.name}, skipping")
                continue
            df = pd.read_csv(csv)
            df['_source'] = str(cd)
            all_dfs.append(df)
            print(f"  Loaded {len(df)} rows from {cd.name}")

    if not all_dfs:
        return None

    combined = pd.concat(all_dfs, ignore_index=True)

    if polarity == 'npp':
        combined = combined[combined['polarity'] == 'npp'].copy()
        combined['dP_work'] = combined['dP_uC_cm2']
    elif polarity == 'pnn':
        combined = combined[combined['polarity'] == 'pnn'].copy()
        combined['dP_work'] = -combined['dP_uC_cm2']
    else:
        combined['dP_work'] = combined['dP_uC_cm2'].copy()
        pnn_mask = combined['polarity'] == 'pnn'
        combined.loc[pnn_mask, 'dP_work'] = -combined.loc[pnn_mask, 'dP_uC_cm2']

    grouped = (combined
               .groupby(['cd_um', 'pulse_width_ns'])['dP_work']
               .agg(dP_mean='mean', dP_std='std', n_devices='count')
               .reset_index())
    return grouped


def get_averaged_data(
    sample: str,
    device=None,
    cd=None,
    meas_type=None,
    meas_name=None,
    pulsetrain=None,
    subdirs_contain=None,
    group_by=None,
    data_root=None,
) -> pd.DataFrame | None:
    """
    Convenience function: trawl a sample, apply filters, and return
    averaged analysis results in one call.

    Examples:
        # Average all C4 shmoos on SGC91-0
        df = get_averaged_data('SGC91-0', device='C4', meas_type='shmoo')

        # Only the 'first pass' sub-run on SNP418, D1, cd9
        df = get_averaged_data('SNP418', subdirs_contain=['first pass', 'D1', 'cd10'],
                               meas_type='shmoo')
    """
    records = trawl(sample, data_root=data_root)
    matched = filter_records(
        records,
        device=device,
        cd=cd,
        meas_type=meas_type,
        meas_name=meas_name,
        pulsetrain=pulsetrain,
        subdirs_contain=subdirs_contain,
    )
    print(f"Matched {len(matched)} analysis file(s) for '{sample}'")
    for r in matched:
        label = '/'.join(r['subdirs'] + [r['meas_name']]) if r['subdirs'] else r['meas_name']
        print(f"  {label}")
    return load_and_average(matched, group_by=group_by)
