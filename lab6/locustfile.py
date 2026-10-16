"""Lab 6: two independent user classes; real HTTP requests and JSON validation."""
import csv
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from locust import HttpUser, between, events, task
from locust.exception import StopUser
from locust.stats import PERCENTILES_TO_REPORT, StatsCSV

LOG = logging.getLogger(__name__)
SYSTEM = os.getenv("BMC_SYSTEM_PATH", "/redfish/v1/Systems/system")


@events.test_stop.add_listener
def save_final_statistics(environment, **kwargs):
    """Periodic CSV may precede final responses; export again after all users stop."""
    prefix = getattr(environment.parsed_options, "csv_prefix", None)
    if prefix:
        destination = Path(str(prefix) + "_final_stats.csv")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="") as stream:
            StatsCSV(environment, PERCENTILES_TO_REPORT).requests_csv(csv.writer(stream))


def local_redfish_path(path):
    parsed = urlsplit(path)
    return not parsed.scheme and not parsed.netloc and path.startswith("/redfish/")


def json_body(response):
    if response.status_code != 200:
        response.failure(f"Expected HTTP 200, got {response.status_code}")
        return None
    try:
        data = response.json()
        if data is None:
            response.failure("Unexpected JSON null")
        return data
    except ValueError:
        response.failure("Invalid JSON")
        return None


class OpenBMCUser(HttpUser):
    host = os.getenv("BMC_URL", "https://127.0.0.1:2443")
    wait_time = between(1, 3)

    def on_start(self):
        self.session_location = None
        self.client.verify = (os.getenv("BMC_CA_BUNDLE") or
                              os.getenv("BMC_VERIFY_TLS", "true").lower() != "false")
        password = os.getenv("BMC_PASSWORD")
        if not password:
            LOG.error("Set BMC_PASSWORD before starting OpenBMCUser")
            raise StopUser()
        with self.client.post("/redfish/v1/SessionService/Sessions", name="BMC login",
                              json={"UserName": os.getenv("BMC_USERNAME", "root"),
                                    "Password": password}, timeout=15,
                              allow_redirects=False, catch_response=True) as response:
            token = response.headers.get("X-Auth-Token")
            location = response.headers.get("Location", "")
            if response.status_code not in (200, 201) or not token or not local_redfish_path(location):
                response.failure(f"Session creation failed: HTTP {response.status_code}")
                raise StopUser()
            self.client.headers["X-Auth-Token"] = token
            self.session_location = location
            response.success()

    def on_stop(self):
        if self.session_location:
            with self.client.delete(self.session_location, name="BMC logout", timeout=15,
                                    allow_redirects=False, catch_response=True) as response:
                if response.status_code not in (200, 204):
                    response.failure(f"Session deletion failed: HTTP {response.status_code}")
            self.session_location = None

    @task(3)
    def system_information(self):
        with self.client.get(SYSTEM, name="BMC system", timeout=15,
                             allow_redirects=False, catch_response=True) as response:
            data = json_body(response)
            if data is None:
                return
            if not isinstance(data, dict) or not isinstance(data.get("Status"), dict):
                response.failure("Missing system Status object")

    @task(2)
    def power_state(self):
        # Same resource, separate business operation and statistics label.
        with self.client.get(SYSTEM, name="BMC PowerState", timeout=15,
                             allow_redirects=False, catch_response=True) as response:
            data = json_body(response)
            if data is None:
                return
            if not isinstance(data, dict) or data.get("PowerState") not in {
                    "On", "Off", "PoweringOn", "PoweringOff"}:
                response.failure("Missing or invalid PowerState")


class PublicAPIUser(HttpUser):
    host = os.getenv("PUBLIC_API_URL", "https://jsonplaceholder.typicode.com")
    wait_time = between(3, 5)

    @task
    def public_api_reads(self):
        with self.client.get("/posts", name="Public posts", timeout=15,
                             catch_response=True) as response:
            data = json_body(response)
            if data is not None and (not isinstance(data, list) or not data or
                    any(not isinstance(post, dict) or not {"id", "title", "body"} <= post.keys()
                        for post in data)):
                response.failure("Invalid posts list")
        # An absolute URL is necessary: wttr.in is a separate host.
        weather = os.getenv("WEATHER_URL", "https://wttr.in/Novosibirsk?format=j1")
        with self.client.get(weather, name="Public weather Novosibirsk", timeout=15,
                             catch_response=True) as response:
            data = json_body(response)
            if data is not None and (not isinstance(data, dict) or
                    not isinstance(data.get("current_condition"), list) or
                    not data["current_condition"] or
                    not isinstance(data["current_condition"][0], dict) or
                    "temp_C" not in data["current_condition"][0]):
                response.failure("Invalid weather current_condition")
