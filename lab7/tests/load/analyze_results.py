"""Analyze Locust exports without inventing samples or combining percentiles."""
import argparse
import csv
import json
from pathlib import Path


def analyze(results, p95_limit):
    summary = []
    for meta_path in sorted(results.glob("*users.json")):
        meta = json.loads(meta_path.read_text())
        stats_path = results / f"{meta['name']}_final_stats.csv"
        with stats_path.open() as stream:
            stats = list(csv.DictReader(stream))
        aggregate = next(row for row in stats if row["Name"] == "Aggregated")
        count, failed = int(aggregate["Request Count"]), int(aggregate["Failure Count"])
        names = {row["Name"] for row in stats if int(row["Request Count"]) > 0}
        required = {"BMC system", "BMC PowerState"} if meta["target"] == "bmc" else {
            "Public posts", "Public weather Novosibirsk"}
        p95 = float(aggregate["95%"])
        with (results / f"{meta['name']}_stats_history.csv").open() as stream:
            peak_users = max((int(row["User Count"]) for row in csv.DictReader(stream)), default=0)
        summary.append({"profile": meta["name"], "target": meta["target"], "users": meta["users"],
                        "requests": count, "failures": failed,
                        "error_percent": 100 * failed / count if count else None,
                        "average_ms": float(aggregate["Average Response Time"]),
                        "p95_ms": p95, "rps": float(aggregate["Requests/s"]),
                        "duration": meta["duration"],
                        "both_operations_exercised": required <= names,
                        "peak_users_observed": peak_users,
                        "stable": (count > 0 and failed == 0 and p95 <= p95_limit and required <= names
                                   and meta["exit_code"] == 0 and peak_users >= meta["users"]),
                        "exit_code": meta["exit_code"]})
    summary.sort(key=lambda row: (row["target"], row["users"]))
    stable = [row["users"] for row in summary if row["target"] == "bmc" and row["stable"]]
    data = {"criteria": {"max_error_percent": 0, "max_p95_ms": p95_limit,
                         "scope": "All requests including session login/logout; both business reads required"},
            "maximum_stable_tested_bmc_users": max(stable) if stable else None,
            "limitation": "Short runs only; the physical maximum and long-term stability are not established",
            "profiles": summary}
    (results / "summary.json").write_text(json.dumps(data, indent=2))
    if summary:
        with (results / "summary.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    return data


def plot(results, data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(9, 7.5), sharex=True, constrained_layout=True)
    for profile in data["profiles"]:
        if profile["target"] != "bmc":
            continue
        with (results / f"{profile['profile']}_stats_history.csv").open() as stream:
            rows = [row for row in csv.DictReader(stream) if row["Name"] == "Aggregated"]
        if not rows:
            continue
        zero = float(rows[0]["Timestamp"])
        times = [float(row["Timestamp"]) - zero for row in rows]
        label = f"{profile['users']} users ({profile['duration']})"
        axes[0].plot(times, [float(row["User Count"]) for row in rows], label=label)
        axes[1].plot(times, [float(row["Requests/s"]) for row in rows], label=label)
        percentile = [float(row["95%"]) if row["95%"] not in {"N/A", ""} else float("nan") for row in rows]
        axes[2].plot(times, percentile, label=label)
    axes[0].set_ylabel("Active users")
    axes[1].set_ylabel("Requests/s (10 s window)")
    axes[2].set_ylabel("p95, ms (10 s window)")
    axes[2].set_xlabel("Seconds since each run started")
    axes[0].set_title("OpenBMC in QEMU: independent load profiles")
    for axis in axes:
        axis.grid(alpha=.25)
        axis.legend(loc="upper left", ncol=3)
    fig.savefig(results / "bmc_load.png", dpi=170)
    fig.savefig(results / "bmc_load.svg")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--p95-limit-ms", type=float, default=5000)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    data = analyze(args.results, args.p95_limit_ms)
    print(json.dumps(data, indent=2))
    if args.plot:
        plot(args.results, data)
