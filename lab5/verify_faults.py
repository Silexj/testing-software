"""Prove that the integration tests detect faults in the local QEMU lab."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import warnings

import requests
import urllib3

HERE = Path(__file__).resolve().parent


def configure(*args):
    subprocess.run([sys.executable, str(HERE / "setup_qemu_lab.py"), *args, "--qemu"],
                   check=True)


def expect_failure(name, test, message, **settings):
    env = {**os.environ, "BMC_URL": "https://127.0.0.1:2443", "BMC_VERIFY_TLS": "false",
           "BMC_POWER_TIMEOUT": "20", **settings}
    result = subprocess.run([sys.executable, "-m", "pytest", str(HERE / "test_redfish.py")
                             + "::" + test, "-v", "--tb=short"],
                            env=env, capture_output=True, text=True, timeout=180)
    output = result.stdout + result.stderr
    (HERE / "results" / (name + ".log")).write_text(output)
    assert result.returncode == 1 and message in output, (
        f"{name}: expected the specific assertion failure {message!r}; see results/{name}.log")
    print(f"{name}: expected fault detected (pytest exit 1)", flush=True)


def wait_temperature(value):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            response = requests.get("https://127.0.0.1:2443/redfish/v1/Chassis/chassis/Thermal",
                                    auth=("root", os.environ["BMC_PASSWORD"]),
                                    verify=False, timeout=15)
        response.raise_for_status()
        sensors = response.json()["Temperatures"]
        if any(s.get("ReadingCelsius") == value for s in sensors):
            return
        time.sleep(1)
    raise RuntimeError("Native hwmon/Redfish did not expose the injected temperature")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, action="store_true")
    parser.parse_args()
    (HERE / "results").mkdir(exist_ok=True)
    try:
        configure("temperature", "--cpu0", "95", "--cpu1", "44")
        wait_temperature(95)
        expect_failure("negative_temperature", "test_cpu_temperature", "unhealthy sensor")
        configure("temperature")
        wait_temperature(42)
        expect_failure("negative_sensor_mapping", "test_cpu_redfish_matches_ipmi",
                       "IPMI match is missing or ambiguous",
                       CPU_SENSOR_MAP='{"0":"missing_cpu_sensor","1":"missing_cpu_sensor"}')
        configure("power-fault", "--fault", "on")
        expect_failure("negative_power", "test_power_on", "PowerState did not become On")
    finally:
        configure("power-fault", "--fault", "off")
        configure("temperature")
        wait_temperature(42)


if __name__ == "__main__":
    main()
