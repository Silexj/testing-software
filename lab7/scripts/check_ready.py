"""Assert that the native Redfish sensor path exposes the installed hardware model."""
import json
import os
from pathlib import Path
import time
import warnings
import requests
import urllib3

out = Path(os.getenv('REPORTS', 'lab7/artifacts')) / 'qemu'
with requests.Session() as http:
    http.auth = (os.environ['BMC_USERNAME'], os.environ['BMC_PASSWORD'])
    deadline = time.monotonic() + 60
    while True:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)
            response = http.get(os.environ['BMC_URL'] + '/redfish/v1/Chassis/chassis/Thermal',
                                verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        values = sorted(s['ReadingCelsius'] for s in data.get('Temperatures', [])
                        if s.get('ReadingCelsius') is not None and
                        s.get('Name', '').replace('_', ' ') in ['p0 core0 temp', 'p1 core0 temp'])
        if values == [42, 44]:
            (out / 'thermal.json').write_text(json.dumps(data, indent=2) + '\n')
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f'The native sensor pipeline is not ready: {values}')
        time.sleep(1)
print('Native hwmon -> Redfish ready: CPU temperatures 42/44 Celsius')
