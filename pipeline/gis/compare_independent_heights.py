"""Compare the authored path with the separate 2016 HRDEM.

This is an epoch-to-epoch diagnostic, not accepted survey control. The older
1 m DTM has unknown local absolute accuracy and can blend walls with pavement.
No path geometry or datum adjustment is made from these residuals.
"""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).resolve().parents[2]


def stats(values):
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(count=0)
    return dict(count=len(values), mean_m=float(np.mean(values)),
                median_m=float(np.median(values)), rms_m=float(np.sqrt(np.mean(values**2))),
                abs_p95_m=float(np.percentile(abs(values), 95)),
                abs_max_m=float(np.max(abs(values))),
                count_above_015m=int(np.count_nonzero(abs(values) > .15)))


def main():
    path_file = ROOT / 'data/derived/paved-circuit-runtime.json'
    reference_file = ROOT / 'data/derived/terrain_2016_reference.npz'
    source = json.loads(path_file.read_text())
    xyz = np.asarray(source['points_local_m'])
    distance = np.asarray(source['chainage_runtime_m'])
    source_distance = np.asarray(source['chainage_source_m'])
    # Fixed 10 m spacing chosen before examining residuals, including both ends.
    stations = np.r_[np.arange(0, distance[-1], 10.), distance[-1]]
    points = np.column_stack([np.interp(stations, distance, xyz[:, i]) for i in range(3)])
    original_stations = np.interp(stations, distance, source_distance)
    with np.load(reference_file) as grid:
        height = RegularGridInterpolator((grid['y'], grid['x']), grid['z'],
                                          bounds_error=False, fill_value=np.nan)
        old_z = height(points[:, [1, 0]])
        offsets = np.array([[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 0],
                            [0, 1], [1, -1], [1, 0], [1, 1]], dtype=float)
        neighbours = height(points[:, None, [1, 0]] + offsets[None])
    spread = np.max(neighbours, axis=1) - np.min(neighbours, axis=1)
    delta = points[:, 2] - old_z
    exclusions = json.loads((ROOT / 'manifests/pavement-review-overrides.json').read_text())
    occluded = np.zeros(len(stations), dtype=bool)
    for span in exclusions['occluded_underpasses']:
        occluded |= ((original_stations >= span['start_m'] - 5) &
                     (original_stations <= span['end_m'] + 5))
    flat = np.isfinite(spread) & (spread <= .2) & ~occluded
    rows = []
    for i, station in enumerate(stations):
        rows.append(dict(runtime_chainage_m=float(station),
                         source_chainage_m=float(original_stations[i]),
                         x_m=float(points[i, 0]), y_m=float(points[i, 1]),
                         authored_height_m=float(points[i, 2]),
                         hrdem_2016_height_m=float(old_z[i]) if np.isfinite(old_z[i]) else None,
                         difference_m=float(delta[i]) if np.isfinite(delta[i]) else None,
                         reference_2m_neighbourhood_range_m=float(spread[i]) if np.isfinite(spread[i]) else None,
                         near_occluded_underpass=bool(occluded[i]),
                         flat_reference_subset=bool(flat[i]),
                         accepted_independent_control=False))
    evidence = ROOT / 'evidence/corridor'
    csv_file = evidence / 'independent-height-comparison.csv'
    with csv_file.open('w', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    hashes = []
    for path in (path_file, reference_file):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        hashes.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=digest))
    report = dict(input_files=hashes, sample_spacing_m=10,
                  difference_sign='authored 2022-based height minus 2016 HRDEM, both CGVD2013',
                  all_samples=stats(delta), outside_underpasses=stats(delta[~occluded]),
                  flat_reference_subset=stats(delta[flat]),
                  flat_rule='Finite 3x3 samples at 1 m offsets; max-minus-min <=0.2 m; outside underpasses plus 5 m margin',
                  worst_samples=sorted([r for r in rows if r['difference_m'] is not None],
                                       key=lambda r: abs(r['difference_m']), reverse=True)[:15],
                  csv=csv_file.relative_to(ROOT).as_posix(),
                  source_url='https://canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-lidar/BC-Lower_Mainland_2016-1m-dtm.tif',
                  accepted_independent_control_count=0,
                  absolute_accuracy_accepted=False,
                  limits=['Local 2016 absolute accuracy and stable physical surfaces are not verified.',
                          'The 1 m raster and reprojection can mix path, walls, cliffs and water.',
                          'Different survey dates can include real change. Underpass ground is not visible from above.',
                          'Agreement is supporting evidence only. Do not select passing points to assert survey accuracy.'])
    (evidence / 'independent-height-comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), dpi=140)
    axes[0].plot(stations, points[:, 2], label='Authored pavement (2022 source)', lw=.8)
    axes[0].plot(stations, old_z, label='Independent 2016 DTM', lw=.8)
    axes[0].set(ylabel='CGVD2013 height (m)')
    axes[0].legend()
    axes[1].plot(stations, delta, lw=.7, label='All sampled stations')
    axes[1].scatter(stations[flat], delta[flat], s=5, label='Predefined flat-reference subset')
    axes[1].axhspan(-.15, .15, alpha=.2, color='green')
    axes[1].set(ylabel='Authored minus 2016 (m)')
    axes[1].legend()
    axes[2].plot(stations, delta, lw=.7)
    axes[2].axhspan(-.15, .15, alpha=.2, color='green')
    axes[2].set(ylabel='Difference, detail (m)', ylim=(-1, 1), xlabel='Authored route chainage (m)')
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle('Independent historical height comparison — diagnostic only; no accepted survey controls')
    fig.tight_layout()
    fig.savefig(evidence / 'independent-height-comparison.png')
    print(json.dumps({k: report[k] for k in ['all_samples', 'outside_underpasses', 'flat_reference_subset',
                                          'accepted_independent_control_count']}, indent=2))


if __name__ == '__main__':
    main()
