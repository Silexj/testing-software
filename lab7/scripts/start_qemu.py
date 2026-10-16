"""Start a fresh disposable OpenBMC in the Jenkins container and await readiness."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import warnings

import requests
import urllib3

ROOT = Path.cwd()
RUNTIME = ROOT / '.runtime'
OUT = ROOT / os.getenv('REPORTS', 'lab7/artifacts') / 'qemu'
SOURCE = Path('/opt/openbmc/romulus.mtd')
FLASH = RUNTIME / 'openbmc.mtd'


def main():
    RUNTIME.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not SOURCE.is_file():
        raise RuntimeError('Mount the lab firmware read-only at /opt/openbmc/romulus.mtd')
    shutil.copyfile(SOURCE, FLASH)
    command = ['qemu-system-arm', '-m', '256', '-M', 'romulus-bmc', '-nographic',
               '-drive', f'file={FLASH},format=raw,if=mtd', '-net', 'nic', '-net',
               'user,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:2443-:443,'
               'hostfwd=udp:127.0.0.1:2623-:623,hostname=qemu']
    env = {**os.environ, 'JENKINS_NODE_COOKIE': 'lab7-owned-qemu'}
    with (OUT / 'console.log').open('w') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True, env=env)
    (RUNTIME / 'qemu.pid').write_text(str(process.pid))
    metadata = {'command': command, 'pid': process.pid, 'firmware_sha256':
                hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'ready': False}
    started = time.monotonic()
    try:
        while time.monotonic() - started < 480:
            if process.poll() is not None:
                raise RuntimeError(f'QEMU exited with code {process.returncode}; see console.log')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)
                    response = requests.get(os.environ['BMC_URL'] + '/redfish/v1/Systems/system',
                                            auth=(os.environ['BMC_USERNAME'], os.environ['BMC_PASSWORD']),
                                            verify=False, timeout=10)
                if response.status_code == 200 and response.json().get('PowerState') == 'Off':
                    with socket.create_connection(('127.0.0.1', 2222), timeout=2):
                        pass
                    metadata.update(ready=True, initial_power_state='Off',
                                    boot_seconds=round(time.monotonic() - started, 2))
                    print('OpenBMC is ready; initial PowerState=Off', flush=True)
                    return
            except (requests.RequestException, ValueError, OSError):
                pass
            time.sleep(3)
        raise RuntimeError('OpenBMC did not become ready in 480 seconds')
    finally:
        (OUT / 'boot.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
