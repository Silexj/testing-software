"""Trigger the dedicated local Jenkins job and download its real build evidence."""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:8080/'
JOB = BASE + 'job/openbmc-lab7/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inject-api-failure', action='store_true')
    parser.add_argument('--collect', type=int, help='Download an existing build instead of triggering one')
    args = parser.parse_args()
    password = (ROOT / '.runtime/lab7/secrets/admin-password').read_text().strip()
    with requests.Session() as http:
        http.auth = ('labadmin', password)
        def get(url):
            response = http.get(url, timeout=30)
            response.raise_for_status()
            return response
        if args.collect:
            number = args.collect
        else:
            crumb = get(BASE + 'crumbIssuer/api/json').json()
            http.headers[crumb['crumbRequestField']] = crumb['crumb']
            job = get(JOB + 'api/json').json()
            parameterized = any(p.get('parameterDefinitions') for p in job.get('property', []))
            if args.inject_api_failure and not parameterized:
                parser.error('Run the first normal build before requesting the failure demonstration')
            endpoint = 'buildWithParameters' if parameterized else 'build'
            response = http.post(JOB + endpoint,
                                 data={'INJECT_API_FAILURE': str(args.inject_api_failure).lower()}, timeout=30)
            response.raise_for_status()
            queue = response.headers['Location']
            deadline = time.monotonic() + 1200
            while True:
                data = get(urljoin(queue, 'api/json')).json()
                if data.get('cancelled'):
                    raise RuntimeError('Jenkins queue item was cancelled')
                if 'executable' in data:
                    number = data['executable']['number']
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Jenkins queue did not start the job')
                time.sleep(3)
        build = JOB + str(number) + '/'
        print(f'Jenkins build #{number}: {build}', flush=True)
        deadline = time.monotonic() + 1260
        while True:
            data = get(build + 'api/json').json()
            if not data['building']:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Jenkins build did not finish')
            time.sleep(5)
        destination = ROOT / 'lab7/results' / f'build-{number}'
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'build.json').write_text(json.dumps(data, indent=2) + '\n')
        (destination / 'console.log').write_bytes(get(build + 'consoleText').content)
        for endpoint, filename in [('wfapi/describe', 'stages.json'), ('testReport/api/json', 'tests.json')]:
            response = http.get(build + endpoint, timeout=30)
            if response.status_code == 200:
                (destination / filename).write_text(json.dumps(response.json(), indent=2) + '\n')
        for artifact in data['artifacts']:
            relative = artifact['relativePath']
            path = destination / relative.removeprefix('lab7/artifacts/')
            assert path.resolve().is_relative_to(destination.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(get(build + 'artifact/' + relative).content)
        print(f"Build result={data['result']}; artifacts={len(data['artifacts'])}; saved to {destination}")
        # A requested failed gate remains FAILURE in Jenkins; the helper only verifies that expectation.
        expected = 'FAILURE' if args.inject_api_failure else 'SUCCESS'
        return int(data['result'] != expected)


if __name__ == '__main__':
    raise SystemExit(main())
