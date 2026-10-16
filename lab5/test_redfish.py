"""Integration tests against a real OpenBMC Redfish/IPMI endpoint (no mocks)."""
import csv
import json
import logging
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest
import requests
import urllib3

LOG = logging.getLogger(__name__)
SYSTEM = os.getenv("BMC_SYSTEM_PATH", "/redfish/v1/Systems/system")


def pytest_addoption(parser):
    # This file is loaded as a plugin by conftest.py.
    parser.addoption("--allow-missing-sensors", action="store_true",
                     help="Skip sensor tests only when the QEMU image exposes no CPU sensors")


@dataclass
class Redfish:
    http: requests.Session
    base: str
    verify: object
    timeout: float
    login_status: int = 0
    location: str = ""

    def request(self, method, path, expected=(200,), **kwargs):
        # Never send a session token to another host supplied in a response.
        parsed = urlsplit(path)
        assert not parsed.scheme and not parsed.netloc and path.startswith("/redfish/"), path
        started = time.monotonic()
        try:
            response = self.http.request(method, self.base + path, timeout=self.timeout,
                                         verify=self.verify, allow_redirects=False, **kwargs)
        except requests.RequestException as exc:
            pytest.fail(f"{method} {path}: {type(exc).__name__}")
        LOG.info("%s %s -> %s (%.3f s)", method, path, response.status_code,
                 time.monotonic() - started)
        assert response.status_code in expected, (
            f"{method} {path}: HTTP {response.status_code}, expected {expected}")
        return response

    def get(self, path):
        response = self.request("GET", path)
        try:
            data = response.json()
        except ValueError:
            pytest.fail(f"GET {path}: response is not JSON")
        assert isinstance(data, dict), f"GET {path}: JSON object expected"
        return data


@pytest.fixture(scope="session")
def redfish():
    password = os.environ.get("BMC_PASSWORD")
    if not password:
        pytest.fail("Set BMC_PASSWORD before running integration tests")
    verify = os.getenv("BMC_CA_BUNDLE") or os.getenv("BMC_VERIFY_TLS", "true").lower() != "false"
    if verify is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    with requests.Session() as http:
        client = Redfish(http, os.getenv("BMC_URL", "https://127.0.0.1:2443").rstrip("/"),
                         verify, float(os.getenv("BMC_TIMEOUT", "30")))
        response = client.request("POST", "/redfish/v1/SessionService/Sessions",
                                  expected=(200, 201), json={
                                      "UserName": os.getenv("BMC_USERNAME", "root"),
                                      "Password": password})
        token = response.headers.get("X-Auth-Token")
        location = response.headers.get("Location")
        assert token, "Missing X-Auth-Token"
        http.headers["X-Auth-Token"] = token
        client.login_status = response.status_code
        try:
            assert location, "Missing session Location"
            client.location = location
            yield client
        finally:
            if client.location:
                client.request("DELETE", client.location, expected=(200, 204))


def test_authentication(redfish):
    """TC-API-01: session creation, token and authenticated session read."""
    assert redfish.login_status in (200, 201)
    assert redfish.http.headers.get("X-Auth-Token")
    data = redfish.get(redfish.location)
    assert data["UserName"] == os.getenv("BMC_USERNAME", "root")


def test_system_information(redfish):
    """TC-API-02: HTTP 200, Status object and a valid PowerState."""
    data = redfish.get(SYSTEM)
    assert isinstance(data.get("Status"), dict), data
    assert data.get("PowerState") in {"On", "Off", "PoweringOn", "PoweringOff"}, data
    LOG.info("System Status=%s PowerState=%s", data["Status"], data["PowerState"])


def wait_power(client, state):
    deadline = time.monotonic() + float(os.getenv("BMC_POWER_TIMEOUT", "90"))
    while True:
        actual = client.get(SYSTEM).get("PowerState")
        if actual == state:
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"PowerState did not become {state}; last value={actual}")
        time.sleep(2)


def test_power_on(redfish):
    """TC-API-03: On action, polling and restoration of initial power state."""
    initial = redfish.get(SYSTEM)["PowerState"]
    assert initial in {"On", "Off"}, f"Host is in transition: {initial}"
    action = SYSTEM + "/Actions/ComputerSystem.Reset"
    # 202 = asynchronous operation, 204 = synchronous completion allowed by Redfish.
    try:
        response = redfish.request("POST", action, expected=(202, 204), json={"ResetType": "On"})
        LOG.info("ResetType=On accepted, HTTP %s; initial=%s", response.status_code, initial)
        wait_power(redfish, "On")
    finally:
        if initial == "Off":
            redfish.request("POST", action, expected=(202, 204), json={"ResetType": "ForceOff"})
            wait_power(redfish, "Off")


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@pytest.fixture(scope="session")
def cpu_sensors(redfish, request):
    sensors = []
    chassis = redfish.get("/redfish/v1/Chassis")
    for member in chassis.get("Members", []):
        data = redfish.get(member["@odata.id"])
        thermal = data.get("Thermal", {}).get("@odata.id")
        if not thermal:
            continue
        for sensor in redfish.get(thermal).get("Temperatures", []):
            name = sensor.get("Name", "")
            if sensor.get("PhysicalContext") == "CPU" or re.search(r"cpu|processor", name, re.I):
                sensors.append(sensor)
    # Empty data is never interpreted as a successful test.
    if not sensors and request.config.getoption("--allow-missing-sensors"):
        pytest.skip("QEMU Romulus exposes no CPU temperature sensors; physical sensor validation unavailable")
    assert sensors, "No CPU sensors found in Chassis/*/Thermal"
    return sensors


def test_cpu_temperature(cpu_sensors):
    """TC-API-04: numeric Celsius reading, health and sensor-provided thresholds."""
    for sensor in cpu_sensors:
        name = sensor.get("Name", sensor.get("MemberId"))
        value = sensor.get("ReadingCelsius")
        assert numeric(value), f"{name}: missing/invalid ReadingCelsius={value}"
        assert sensor.get("Status", {}).get("State") == "Enabled", f"{name}: sensor not enabled"
        assert sensor.get("Status", {}).get("Health") == "OK", f"{name}: unhealthy sensor"
        limits = 0
        for key in ("UpperThresholdNonCritical", "UpperThresholdCritical", "UpperThresholdFatal",
                    "LowerThresholdNonCritical", "LowerThresholdCritical", "LowerThresholdFatal"):
            threshold = sensor.get(key)
            if threshold is None:
                continue
            assert numeric(threshold), f"{name}: invalid {key}"
            limits += 1
            assert (value < threshold if key.startswith("Upper") else value > threshold), (
                f"{name}: {value} Celsius violates {key}={threshold}")
        assert limits, f"{name}: no thresholds; temperature norm cannot be established"
        LOG.info("CPU sensor %s = %s Celsius; %s thresholds checked", name, value, limits)


def test_cpu_redfish_matches_ipmi(redfish, cpu_sensors):
    """TC-API-05: match every CPU temperature by explicit map or unique name."""
    env = os.environ.copy()
    env["IPMI_PASSWORD"] = os.environ.get("IPMI_PASSWORD", os.environ["BMC_PASSWORD"])
    command = ["ipmitool", "-I", "lanplus", "-H", os.getenv("IPMI_HOST", "127.0.0.1"),
               "-p", os.getenv("IPMI_PORT", "2623"), "-U", os.getenv("IPMI_USERNAME", "root"),
               "-E", "-c", "sensor", "list"]
    # Bracket the IPMI sample with two Redfish samples to account for temperature drift.
    before = {s["MemberId"]: s for s in cpu_sensors}
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.fail(f"IPMI read failed: {type(exc).__name__}")
    assert result.returncode == 0, f"ipmitool failed with exit code {result.returncode}"
    rows = list(csv.reader(result.stdout.splitlines()))
    mapping = json.loads(os.getenv("CPU_SENSOR_MAP", "{}"))
    tolerance = float(os.getenv("CPU_TOLERANCE_C", "2"))
    assert math.isfinite(tolerance) and tolerance >= 0
    normalize = lambda name: re.sub(r"[^a-z0-9]", "", name.lower())
    # Refresh the fixture's reads for temporal comparison.
    after = {}
    for member in redfish.get("/redfish/v1/Chassis")["Members"]:
        thermal = redfish.get(member["@odata.id"]).get("Thermal", {}).get("@odata.id")
        if thermal:
            for sensor in redfish.get(thermal).get("Temperatures", []):
                after[sensor["MemberId"]] = sensor
    for key, sensor in before.items():
        expected_name = mapping.get(key, sensor["Name"])
        matched = [row for row in rows if len(row) >= 4 and normalize(row[0]) == normalize(expected_name)]
        assert len(matched) == 1, f"{sensor['Name']}: IPMI match is missing or ambiguous; set CPU_SENSOR_MAP"
        row = matched[0]
        assert row[2].strip().lower() in {"degrees c", "degrees celsius"}, row
        assert row[3].strip().lower() == "ok", f"IPMI sensor status is {row[3]}"
        value = float(row[1])
        low, high = sensor.get("ReadingCelsius"), after.get(key, {}).get("ReadingCelsius")
        assert numeric(value) and numeric(low) and numeric(high), f"Unavailable reading: {key}"
        assert min(low, high) - tolerance <= value <= max(low, high) + tolerance, (
            f"{key}: Redfish {low}/{high} C, IPMI {value} C, tolerance {tolerance} C")
        LOG.info("%s: Redfish %s/%s C, IPMI %s C, tolerance %s C", key, low, high, value, tolerance)
