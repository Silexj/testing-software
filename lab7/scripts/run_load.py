"""Run the real lab 6 BMC workload and convert measured gates to JUnit."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

out = Path(os.getenv('REPORTS', 'lab7/artifacts')) / 'load'
out.mkdir(parents=True, exist_ok=True)
prefix = out / 'bmc'
started = time.monotonic()
command = [sys.executable, '-m', 'locust', '-f', 'lab7/tests/load/locustfile.py', 'OpenBMCUser',
           '--headless', '--users', '10', '--spawn-rate', '2', '--run-time', '30s',
           '--stop-timeout', '20', '--only-summary', '--csv', str(prefix),
           '--csv-full-history', '--html', str(prefix) + '.html']
with (out / 'locust.log').open('w') as log:
    process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=100)
summary = {'users': 10, 'duration_seconds': 30, 'locust_exit_code': process.returncode}
try:
    with Path(str(prefix) + '_final_stats.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    total = next(row for row in rows if row['Name'] == 'Aggregated')
    with Path(str(prefix) + '_stats_history.csv').open() as stream:
        peak = max(int(row['User Count']) for row in csv.DictReader(stream))
    counts = {row['Name']: int(row['Request Count']) for row in rows}
    failures = int(total['Failure Count'])
    summary.update(requests=int(total['Request Count']), failures=failures,
                   average_ms=float(total['Average Response Time']), p95_ms=float(total['95%']),
                   rps=float(total['Requests/s']), peak_users=peak,
                   logins=counts.get('BMC login', 0), logouts=counts.get('BMC logout', 0))
    gates = {
        'locust_process': process.returncode == 0,
        'both_read_operations': all(counts.get(name, 0) > 0 for name in ['BMC system', 'BMC PowerState']),
        'ten_concurrent_users': peak >= 10,
        'zero_request_failures': summary['requests'] > 0 and failures == 0,
        'p95_at_most_5000ms': summary['p95_ms'] <= 5000,
        'all_sessions_closed': summary['logins'] == summary['logouts'] == 10,
    }
except (OSError, ValueError, KeyError, StopIteration) as exc:
    summary['error'] = str(exc)
    gates = {'valid_locust_exports': False}
summary['gates'] = gates
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
failed = sum(not passed for passed in gates.values())
suite = ET.Element('testsuite', name='Locust acceptance gates', tests=str(len(gates)),
                   failures=str(failed), errors='0', skipped='0',
                   time=f'{time.monotonic() - started:.3f}')
for name, passed in gates.items():
    case = ET.SubElement(suite, 'testcase', classname='load', name=name)
    if not passed:
        ET.SubElement(case, 'failure', message='Measured load criterion failed').text = json.dumps(summary)
ET.ElementTree(suite).write(out / 'junit.xml', encoding='utf-8', xml_declaration=True)
print(json.dumps(summary, indent=2))
raise SystemExit(bool(failed))
