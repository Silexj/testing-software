"""Reproducible short runs; save unmodified Locust CSV, HTML, log and metadata."""
import argparse
import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["bmc", "public"])
    parser.add_argument("--users", type=int, nargs="+", default=None)
    parser.add_argument("--duration", default="30s")
    parser.add_argument("--spawn-rate", type=float, default=2)
    parser.add_argument("--prefix", default=None)
    args = parser.parse_args()
    if args.target == "bmc" and not os.getenv("BMC_PASSWORD"):
        parser.error("Set BMC_PASSWORD")
    users = args.users or ([1, 5, 10] if args.target == "bmc" else [1])
    if min(users) < 1 or args.spawn_rate <= 0:
        parser.error("Users and spawn rate must be positive")
    here = Path(__file__).resolve().parent
    results = here / "results"
    results.mkdir(exist_ok=True)
    entries = []
    for count in users:
        name = f"{args.prefix or args.target}_{count}users"
        prefix = results / name
        command = [sys.executable, "-m", "locust", "-f", str(here / "locustfile.py"),
                   "OpenBMCUser" if args.target == "bmc" else "PublicAPIUser",
                   "--headless", "--users", str(count), "--spawn-rate", str(args.spawn_rate),
                   "--run-time", args.duration, "--stop-timeout", "20", "--only-summary",
                   "--csv", str(prefix), "--csv-full-history", "--html", str(prefix) + ".html"]
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(f"Running {name}, duration={args.duration}, rate={args.spawn_rate}", flush=True)
        with prefix.with_suffix(".log").open("w") as log:
            result = subprocess.run(command, cwd=here, stdout=log, stderr=subprocess.STDOUT)
        entry = {"name": name, "target": args.target, "users": count,
                 "spawn_rate": args.spawn_rate, "duration": args.duration,
                 "started_at_utc": started, "exit_code": result.returncode,
                 "locust_version": importlib.metadata.version("locust"),
                 "python_version": sys.version.split()[0],
                 "bmc_url": os.getenv("BMC_URL", "https://127.0.0.1:2443"),
                 "public_url": os.getenv("PUBLIC_API_URL", "https://jsonplaceholder.typicode.com"),
                 "weather_url": os.getenv("WEATHER_URL", "https://wttr.in/Novosibirsk?format=j1")}
        prefix.with_suffix(".json").write_text(json.dumps(entry, indent=2))
        entries.append(entry)
        print(f"Completed {name}, exit={result.returncode}", flush=True)
    return int(any(entry["exit_code"] != 0 for entry in entries))


if __name__ == "__main__":
    raise SystemExit(main())
