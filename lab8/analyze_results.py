"""Validate native profiling exports and summarize real measurements; no fabricated fallbacks."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent


def read_json(path):return json.loads(path.read_text())


def perf_counters(path):
    totals={event:0 for event in ['cycles','instructions','cache-misses']}
    details=[]
    for row in csv.reader(path.open(),delimiter=';'):
        if len(row)<3 or row[0].startswith('#'):continue
        name=next((event for event in totals if event in row[2].split('/')),None)
        if name is None:continue
        # Hybrid CPUs expose cpu_core and cpu_atom separately. Inactive PMUs
        # can be 'not counted'; at least one numeric counter is required per event.
        value=float(row[0]) if not row[0].startswith('<') else None
        details.append({'event':row[2],'value':value,'running_pct':float(row[4]) if len(row)>4 and row[4] else None})
        if value is not None:totals[name]+=value
    assert all(value>0 for value in totals.values()),f'Missing hardware counters: {path}'
    return {**totals,'ipc':totals['instructions']/totals['cycles'],'pmus':details}


def nmon_network(path):
    headers=None; values=[]
    for row in csv.reader(path.open()):
        if row and row[0]=='NET':
            if row[1].startswith('T'):
                assert headers is not None
                values.append({key:float(v) for key,v in zip(headers,row[2:])})
            else:headers=row[2:]
    assert values and headers,f'No nmon NET samples: {path}'
    return {'samples':len(values),'mean_kib_s':{key:statistics.mean(row[key] for row in values) for key in headers}}


def vmstat_stats(path):
    columns=None;rows=[]
    for line in path.read_text().splitlines():
        parts=line.split()
        if 'us' in parts and 'sy' in parts and 'id' in parts:columns=parts;continue
        if columns and len(parts)==len(columns) and all(v.replace('.','',1).isdigit() for v in parts):
            rows.append(dict(zip(columns,map(float,parts))))
    # The first vmstat row averages time since boot and is not a phase sample.
    rows=rows[1:]
    assert rows
    return {'samples':len(rows),'cpu_busy_pct':statistics.mean(100-r['id']-r['wa'] for r in rows),
            'iowait_pct':statistics.mean(r['wa'] for r in rows)}


def summarize(directory):
    env=read_json(directory/'environment.json');assert env['ready']
    assert read_json(directory/'cleanup.json')['qemu_stopped']
    assert read_json(directory/'system-before.json')['PowerState']=='Off'
    assert read_json(directory/'system-after.json')['PowerState']=='Off'
    phases={}
    for phase in ['idle','load']:
        path=directory/phase;rows=list(csv.DictReader((path/'samples.csv').open()))
        assert len(rows)==env['phase_seconds']
        samples={key:[float(row[key]) for row in rows] for key in rows[0] if key!='elapsed_s'}
        assert all(0<=v<=100 for v in samples['host_cpu_busy_pct'])
        assert all(v>0 for v in samples['qemu_rss_mib'])
        assert not any(read_json(path/'exit-codes.json').values())
        phases[phase]={key:{'mean':statistics.mean(values),'min':min(values),'max':max(values)} for key,values in samples.items()}
        phases[phase]['perf']=perf_counters(path/'perf.csv')
        phases[phase]['vmstat']=vmstat_stats(path/'vmstat.log')
        phases[phase]['network']=nmon_network(path/'network.nmon')
        assert phases[phase]['vmstat']['samples']>=env['phase_seconds']-1
        assert phases[phase]['network']['samples']>=env['phase_seconds']-1
        assert abs(phases[phase]['vmstat']['cpu_busy_pct']-phases[phase]['host_cpu_busy_pct']['mean'])<3
    path=directory/'load'
    rows=list(csv.DictReader((path/'bmc_final_stats.csv').open()))
    total=next(r for r in rows if r['Name']=='Aggregated');counts={r['Name']:int(r['Request Count']) for r in rows}
    peak=max(int(row['User Count']) for row in csv.DictReader((path/'bmc_stats_history.csv').open()))
    load={'requests':int(total['Request Count']),'failures':int(total['Failure Count']),
          'average_ms':float(total['Average Response Time']),'p95_ms':float(total['95%']),
          'rps':float(total['Requests/s']),'peak_users':peak,
          'logins':counts.get('BMC login',0),'logouts':counts.get('BMC logout',0)}
    assert load['requests']>0 and load['failures']==0
    assert peak==10 and load['logins']==load['logouts']==10
    assert all(counts.get(k,0)>0 for k in ['BMC system','BMC PowerState'])
    return {'environment':env,'phases':phases,'load':load}


def main():
    experiments={directory.name:summarize(directory) for directory in (ROOT/'results').iterdir()
                 if directory.is_dir() and (directory/'environment.json').exists()}
    assert experiments,'No experiments found'
    if 'baseline' in experiments and 'tb64' in experiments:
        a,b=experiments['baseline'],experiments['tb64']
        for key in ['firmware_sha256','phase_seconds','warmup_seconds','image_id','logical_cpus']:
            assert a['environment'][key]==b['environment'][key],f'Comparison mismatch: {key}'
    (ROOT/'results/summary.json').write_text(json.dumps(experiments,indent=2,ensure_ascii=False)+'\n')
    lines=['# Сводка профилирования','', '| Конфигурация / этап | CPU хоста, % | CPU QEMU, % одного ядра | RSS QEMU, MiB |',
           '|---|---:|---:|---:|']
    for name,result in experiments.items():
        for phase,values in result['phases'].items():
            lines.append(f"| {name} / {phase} | {values['host_cpu_busy_pct']['mean']:.2f} | {values['qemu_cpu_one_core_pct']['mean']:.2f} | {values['qemu_rss_mib']['mean']:.2f} |")
    (ROOT/'results/summary.md').write_text('\n'.join(lines)+'\n')
    files=sorted(p for p in (ROOT/'results').rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (ROOT/'results/SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT/"results")}\n' for p in files))
    print('\n'.join(lines));print('All measurement and workload checks passed.')


if __name__=='__main__':main()
