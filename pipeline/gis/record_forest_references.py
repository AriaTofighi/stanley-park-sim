"""Record inspected, dated forest references. Does not remove canopy objects."""
from pathlib import Path
from datetime import datetime, timezone
from acquire_sources import save_json, digest

ROOT=Path(__file__).resolve().parents[2]
base='https://vancouver.ca/'
files=[
    ('phase-3-map-of-mitigation-work.pdf','2026-01-12','Phase 3 treatment areas; planned extent, not a tree-removal inventory'),
    ('stanley-park-hemlock-looper-report.pdf','2024-01-24','2023 forest assessment; 121 plots and historic condition maps'),
]
sources=[]
for filename,date,use in files:
    path=ROOT/'data/raw/forest'/filename
    sources.append(dict(url=base+'files/cov/'+filename,path=path.relative_to(ROOT).as_posix(),
        sha256=digest(path),bytes=path.stat().st_size,document_date=date,
        coverage='Stanley Park forest',intended_use=use,
        rights='Reference only. No report/map image or extracted map polygon is distributed in the game.',
        delivery='Normal browser download from a link on the City forest management page'))
record=dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),target_period='September 2026',
    sources=sources,progress_page=dict(url=base+'parks-recreation-culture/stanley-park-forest-management.aspx',
        retrieved_date='2026-09-26 America/Los_Angeles',page_date='No explicit modification date',
        rights='Reference only',coverage='Park-wide work summaries',
        method='Read visible Progress and Traffic impacts sections through the browser'),
    completed_phases=[
        dict(phase='1',period='2023-10/2024-04',hectares=67,trees_removed_or_treated=7201,
             areas=['Causeway','Prospect Point','Train precinct','Pipeline Road','sections of Stanley Park Drive']),
        dict(phase='2',period='2024-10/2024-12',hectares=41,trees_removed_or_treated=1329,
             areas=['Aquarium','Brockton Point','Chickadee Trail','seawall-adjacent forest']),
        dict(phase='3 first stage',period='2026-01/2026-04',hectares=34,trees_removed_or_treated=2982,
             areas=['Lovers Walk','Tatlow Walk','Lake Trail','western internal trail areas']),
    ],
    future_work=dict(phase='3 final stage',announced_period='2026 autumn/2027 spring',
                     location='Eastern internal trail areas',completed_as_of_target=False,
                     limit='The page says work will resume. No dated completion record was obtained.'),
    unresolved=[
        'Page headline totals differ from the sum of its detailed completed phase counts. Do not force agreement.',
        'Removed-or-treated tree counts do not identify removed crown locations or canopy area.',
        'The 14,362 authoring canopy envelopes are clusters, not individual trees.',
        'The treatment map includes work not yet evidenced as complete at the target date.',
        'Exact September 2026 canopy openings need newer imagery or dated site evidence.',
    ],
    authoring_action='Retain immutable 2022 canopy data; current vegetation acceptance stays open.',
    accepted_current_canopy=False)
save_json(ROOT/'manifests/forest-condition-sources.json',record)
print('Recorded three dated forest sources; no canopy geometry changed.')
