"""Profile only this lab's QEMU: perf, vmstat, nmon, RSS and a real Locust workload."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'testing-software-qemu:lab8'
LABEL = 'testing-software.lab=8'
BASE = 'https://127.0.0.1:2443'


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          stdout=subprocess.PIPE, **kwargs).stdout.strip()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def cpu_ticks():
    return [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]


def proc_values(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return int(fields[11]) + int(fields[12]), int(fields[21]) * os.sysconf('SC_PAGE_SIZE') / 2**20, fields[19]


def measure(pid, destination, seconds, perf, nmon, password, load):
    destination.mkdir(parents=True)
    env = {**os.environ, 'LC_ALL': 'C', 'BMC_URL': BASE, 'BMC_USERNAME': 'root',
           'BMC_PASSWORD': password, 'BMC_VERIFY_TLS': 'false'}
    commands = {
        'perf': [perf, 'stat', '--no-scale', '-x', ';', '-e', 'cycles:u,instructions:u,cache-misses:u',
                 '-p', str(pid), '-o', str(destination/'perf.csv'), '--', 'sleep', str(seconds)],
        'vmstat': ['vmstat', '-w', '1', str(seconds+1)],
        'nmon': [nmon, '-F', str(destination/'network.nmon'), '-s', '1', '-c', str(seconds+1), '-p'],
    }
    if load:
        commands['locust'] = [sys.executable, '-m', 'locust', '-f', str(ROOT/'lab8/locustfile.py'),
            'OpenBMCUser', '--headless', '--users', '10', '--spawn-rate', '2',
            '--run-time', f'{seconds}s', '--stop-timeout', '20', '--only-summary',
            '--csv', str(destination/'bmc'), '--csv-full-history', '--html', str(destination/'bmc.html')]
    write_json(destination/'commands.json', commands)
    processes = {}
    streams = []
    nmon_pid = None
    try:
        nmon_output = command(commands['nmon'], env=env)
        nmon_pid = int(nmon_output.splitlines()[-1])
        # nmon inventories host devices before collecting. Align the measured
        # phase with its first completed snapshot and discard that snapshot.
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            path=destination/'network.nmon'
            if path.exists() and 'NET,T0001,' in path.read_text():break
            time.sleep(.1)
        else:raise RuntimeError('nmon did not produce its first snapshot')
        for name in ['perf', 'vmstat'] + (['locust'] if load else []):
            stream = (destination/(name+'.log')).open('w'); streams.append(stream)
            processes[name] = subprocess.Popen(commands[name], stdout=stream, stderr=subprocess.STDOUT, env=env)
        started = time.monotonic()
        before_cpu = cpu_ticks(); before_proc, _, identity = proc_values(pid); last = started
        with (destination/'samples.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['elapsed_s','host_cpu_busy_pct','host_iowait_pct',
                'qemu_cpu_one_core_pct','qemu_rss_mib'])
            writer.writeheader()
            for i in range(seconds):
                time.sleep(max(0, started+i+1-time.monotonic()))
                now = time.monotonic(); current_cpu = cpu_ticks(); current_proc, rss, current_identity = proc_values(pid)
                if current_identity != identity:
                    raise RuntimeError('QEMU PID changed during measurement')
                delta = [b-a for a,b in zip(before_cpu,current_cpu)]; total = sum(delta)
                writer.writerow({'elapsed_s':round(now-started,4),
                    'host_cpu_busy_pct':round(100*(total-delta[3]-delta[4])/total,4),
                    'host_iowait_pct':round(100*delta[4]/total,4),
                    'qemu_cpu_one_core_pct':round(100*(current_proc-before_proc)/os.sysconf('SC_CLK_TCK')/(now-last),4),
                    'qemu_rss_mib':round(rss,4)})
                stream.flush(); before_cpu=current_cpu;before_proc=current_proc;last=now
        codes = {name:proc.wait(timeout=40) for name,proc in processes.items()}
        write_json(destination/'exit-codes.json', codes)
        if any(codes.values()):
            raise RuntimeError(f'Measurement commands failed: {codes}')
        # nmon forks; wait for its last timestamp and final newline before analysis.
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            contents=(destination/'network.nmon').read_text()
            if f'NET,T{seconds+1:04d},' in contents:
                break
            time.sleep(.2)
        else:
            raise RuntimeError('nmon did not finish the requested snapshots')
    finally:
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate();proc.wait(timeout=10)
        for stream in streams:stream.close()
        # Stop only the PID returned by this phase's nmon invocation, if still alive.
        if nmon_pid:
            try:
                if Path(f'/proc/{nmon_pid}/comm').read_text().strip() == 'nmon':
                    os.kill(nmon_pid,signal.SIGUSR2)
            except FileNotFoundError:pass


def experiment(args, name, tb_size, password):
    destination = ROOT/'lab8/results'/name
    if destination.exists():
        raise RuntimeError(f'{destination} already exists; use a new --run-name instead of overwriting evidence')
    destination.mkdir(parents=True)
    runtime = ROOT/'.runtime/lab8'/name; runtime.mkdir(parents=True, exist_ok=True)
    flash = runtime/'openbmc.mtd';shutil.copyfile(args.firmware,flash)
    container = 'testing-software-lab8-'+name.replace('_','-')
    qemu = ['-m','256','-M','romulus-bmc','-display','none','-serial','stdio','-monitor','none',
        '-accel','tcg'+(f',tb-size={tb_size}' if tb_size else ''),
        '-drive','file=/work/openbmc.mtd,format=raw,if=mtd','-net','nic','-net',
        'user,hostfwd=tcp:0.0.0.0:2443-:443,hostname=qemu']
    launch = ['docker','run','-d','--name',container,'--label',LABEL,
        '--user',f'{os.getuid()}:{os.getgid()}','--cap-drop','ALL','--security-opt','no-new-privileges',
        '-p','127.0.0.1:2443:2443','-v',f'{runtime}:/work:Z',IMAGE]+qemu
    created=False
    metadata={'firmware_sha256':hashlib.sha256(args.firmware.read_bytes()).hexdigest(),
        'docker_command':launch,'qemu_arguments':qemu,'tb_size_mib':tb_size,
        'logical_cpus':os.cpu_count(),'kernel':platform.release(),
        'perf_event_paranoid':Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),
        'phase_seconds':args.seconds,'warmup_seconds':args.warmup,'ready':False}
    try:
        command(launch);created=True
        pid=int(command(['docker','inspect','--format','{{.State.Pid}}',container]))
        metadata['qemu_host_pid']=pid
        metadata['image_id']=command(['docker','image','inspect','--format','{{.Id}}',IMAGE])
        metadata['qemu_version']=command(['docker','exec',container,'qemu-system-arm','--version'])
        metadata['perf_version']=command([args.perf,'--version'])
        metadata['locust_version']=command([sys.executable,'-m','locust','--version'])
        (destination/'host-cpu.txt').write_text(command(['lscpu'])+'\n')
        started=time.monotonic()
        while time.monotonic()-started<480:
            if command(['docker','inspect','--format','{{.State.Running}}',container])!='true':
                raise RuntimeError('QEMU exited before OpenBMC became ready')
            try:
                response=requests.get(BASE+'/redfish/v1/Systems/system',auth=('root',password),verify=False,timeout=5)
                if response.status_code==200 and response.json().get('PowerState')=='Off':
                    metadata.update(ready=True,boot_seconds=round(time.monotonic()-started,2))
                    write_json(destination/'system-before.json',response.json()); break
            except (requests.RequestException,ValueError):pass
            time.sleep(3)
        else:raise TimeoutError('OpenBMC did not become ready')
        write_json(destination/'environment.json',metadata)
        print(f'{name}: OpenBMC ready, warmup {args.warmup}s',flush=True)
        time.sleep(args.warmup)
        for phase in ['idle','load']:
            print(f'{name}: collecting {phase}, {args.seconds}s',flush=True)
            measure(pid,destination/phase,args.seconds,args.perf,args.nmon,password,phase=='load')
        response=requests.get(BASE+'/redfish/v1/Systems/system',auth=('root',password),verify=False,timeout=10)
        response.raise_for_status();write_json(destination/'system-after.json',response.json())
        assert response.json()['PowerState']=='Off'
    finally:
        write_json(destination/'environment.json',metadata)
        if created:
            (destination/'qemu-console.log').write_text(command(['docker','logs',container],stderr=subprocess.STDOUT)+'\n')
            # Restrict cleanup to the container created by this invocation.
            assert command(['docker','inspect','--format','{{index .Config.Labels "testing-software.lab"}}',container])=='8'
            command(['docker','stop','-t','10',container])
            stopped=command(['docker','inspect','--format','{{.State.Running}}',container])=='false'
            write_json(destination/'cleanup.json',{'qemu_stopped':stopped,'container':container})
            command(['docker','rm',container])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware',type=Path)
    parser.add_argument('--perf',default=shutil.which('perf'))
    parser.add_argument('--nmon',default=shutil.which('nmon'))
    parser.add_argument('--password-file',type=Path)
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--warmup',type=int,default=30)
    parser.add_argument('--run-name',default='baseline')
    parser.add_argument('--tb-size',type=int,help='Optional TCG cache cap in MiB for a separate comparison')
    args=parser.parse_args()
    if not args.perf or not args.nmon:parser.error('Install perf and nmon, or pass absolute executable paths')
    if args.seconds<10 or args.warmup<0:parser.error('Use seconds >= 10 and warmup >= 0')
    if not args.run_name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in args.run_name):
        parser.error('run-name must contain only lowercase ASCII letters, numbers, underscore or hyphen')
    password=args.password_file.read_text().strip() if args.password_file else os.environ.get('BMC_PASSWORD')
    if not password:parser.error('Set BMC_PASSWORD or --password-file (the secret is never saved in evidence)')
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    experiment(args,args.run_name,args.tb_size,password)
    print('Measurements saved. Run python lab8/analyze_results.py',flush=True)


if __name__=='__main__':main()
