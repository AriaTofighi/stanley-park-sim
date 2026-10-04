"""Check and plot retained route samples. Does not operate the application."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def analyse(trace,world,output):
    data=json.loads(trace.read_text(encoding='utf-8-sig'))
    if data['scenario']!='full-circuit-normal-inputs-v1':raise ValueError('A full-circuit trace is required')
    graph=json.loads(world.read_text())
    route=next(row for row in graph['routes'] if row['id']=='main_circuit')
    xyz=np.asarray(route['points'],float)/100
    length=float(np.linalg.norm(np.diff(xyz,axis=0),axis=1).sum())
    samples=data['samples']
    xy=np.array([[p['east_cm'],p['north_cm']] for p in samples])/100
    stations=np.array([p['chainage_m'] for p in samples])
    times=np.array([p['seconds'] for p in samples])
    walking=np.array([p['walking'] for p in samples],bool)
    gates=np.arange(50,length,50)
    nearest=np.min(np.abs(stations[:,None]-gates[None,:]),axis=0)
    transitions=np.flatnonzero(np.diff(walking.astype(int)))+1
    record=dict(trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
        world_sha256=hashlib.sha256(world.read_bytes()).hexdigest(),
        reference_scope='Retained runtime route; this check does not accept geographic accuracy.',
        route_length_m=length,samples=len(samples),
        expected_gates=len(gates),sampled_gates_within_5m=int((nearest<=5).sum()),
        maximum_gate_sample_gap_m=float(nearest.max(initial=0)),
        maximum_sample_interval_seconds=float(np.diff(times).max(initial=0)),
        transitions=[dict(seconds=float(times[i]),chainage_m=float(stations[i]),walking=bool(walking[i])) for i in transitions],
        completed=data['completed'],controller_pass=data.get('full_circuit_check_pass',False),
        sampled_coverage_pass=bool(data['completed'] and np.all(nearest<=5) and len(transitions)==6),
        geographic_acceptance=False)
    output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(13,8),dpi=150,gridspec_kw={'width_ratios':[1.25,1]})
    axes[0].plot(xyz[:,1],xyz[:,0],color='#81919b',lw=3,label='Authored circuit')
    axes[0].plot(xy[:,0],xy[:,1],color='#20627b',lw=1,label='Recorded rider')
    axes[0].scatter(xy[walking,0],xy[walking,1],s=3,c='#b65d1b',label='Walking')
    axes[0].set(xlabel='Local east (m)',ylabel='Local north (m)',title='Full circuit: retained application positions')
    axes[0].axis('equal');axes[0].legend(loc='lower left');axes[0].grid(alpha=.2)
    axes[1].plot(times/60,stations/1000,color='#20627b',lw=1)
    axes[1].scatter(times[walking]/60,stations[walking]/1000,s=3,c='#b65d1b')
    axes[1].set(xlabel='Elapsed minutes',ylabel='Route chainage (km)',title='Progress and walking sections')
    axes[1].grid(alpha=.2)
    fig.suptitle('Controller coverage evidence — survey accuracy remains unaccepted')
    fig.tight_layout();fig.savefig(output.with_suffix('.png'))
    print(json.dumps(record,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('world',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();analyse(a.trace,a.world,a.output)
