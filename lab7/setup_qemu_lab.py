"""Install an explicit hardware model into the local, pinned OpenBMC QEMU lab.

Stock bmcweb, ipmid, hwmon and state-manager remain in use. No API mock server.
Runtime unit overrides replace the absent PSU/FSI/VRM hardware operations only.
"""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import paramiko

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REMOTE = "/run/lab5-hardware"
STAND = HERE / "stand"
CACHE = ROOT / ".runtime/lab5-build"
PLUGIN = "/usr/lib/ipmid-providers/libzz-lab5-scale.so"
HARDWARE_UNITS = [
    "avsbus-enable@0.service", "avsbus-disable@0.service", "fsi-scan@0.service",
    "vrm-control@0.service", "start_host@0.service", "cfam_override@0.service",
    "op-cfam-reset.service", "op-continue-mpreboot@0.service",
    "op-stop-instructions@0.service",
    "mboxd-reload@0.service", "mapper-wait@-org-openbmc-mboxd.service",
]
POWER_UNITS = {
    "obmc-power-start@0.service": "power On",
    "obmc-power-stop@0.service": "power Off",
    "phosphor-wait-power-on@0.service": "wait On",
    "phosphor-wait-power-off@0.service": "wait Off",
}
SERVICES = ["lab5-cpu-sensors.service", "lab5-associations.service"]


def run(client, command, check=True):
    _, out, err = client.exec_command(command, timeout=90)
    stdout, stderr = out.read().decode(), err.read().decode()
    status = out.channel.recv_exit_status()
    if check and status:
        raise RuntimeError(f"Remote command failed ({status}): {command}\n{stdout}{stderr}")
    return stdout


def write(client, path, content, executable=False):
    parent = str(Path(path).parent)
    run(client, "mkdir -p " + shlex.quote(parent))
    with client.open_sftp() as sftp:
        with sftp.open(path, "w") as stream:
            stream.write(content)
        if executable:
            sftp.chmod(path, 0o755)


def compile_helpers(client):
    CACHE.mkdir(parents=True, exist_ok=True)
    with client.open_sftp() as sftp:
        sftp.get("/usr/lib/libsystemd.so.0", str(CACHE / "libsystemd.so.0"))
    for name in ["associations.c", "ipmi_scale_compat.cpp", "romulus_sensor_types.hpp", "build.sh"]:
        shutil.copy2(STAND / name, CACHE / name)
    subprocess.run(["sh", "build.sh"], cwd=CACHE, check=True)



def install(client, build):
    release = run(client, "cat /etc/os-release")
    if 'OPENBMC_TARGET_MACHINE="romulus"' not in release or 'BUILD_ID="20250902012112"' not in release:
        raise RuntimeError("This hardware profile and IPMI ABI fix require Romulus BUILD_ID=20250902012112")
    state = run(client, "busctl get-property xyz.openbmc_project.State.Host "
                "/xyz/openbmc_project/state/host0 xyz.openbmc_project.State.Host CurrentHostState")
    if not state.strip().endswith('.Off"'):
        raise RuntimeError("Stop the emulated host before installing this hardware profile")
    if build:
        compile_helpers(client)
    for name in ["associations", "libzz-lab5-scale.so"]:
        if not (CACHE / name).exists():
            raise RuntimeError("Compiled helpers missing. Run install --qemu --build")
    run(client, "systemctl stop " + " ".join(SERVICES), check=False)
    # Discard only the transient probe service owned by this lab, if present.
    run(client, "rm -f /run/systemd/transient/lab5-cpu-sensors.service", check=False)
    write(client, REMOTE + "/board.sh", (STAND / "board.sh").read_text(), True)
    write(client, REMOTE + "/power.state", "Off\n")
    run(client, "rm -f " + REMOTE + "/fault_power_on")
    write(client, REMOTE + "/hwmon0/temp1_input", "42000\n")
    write(client, REMOTE + "/hwmon0/temp2_input", "44000\n")
    run(client, f"mkdir -p {REMOTE}/device/driver; ln -sfn ../device {REMOTE}/hwmon0/device")
    with client.open_sftp() as sftp:
        sftp.put(str(CACHE / "associations"), REMOTE + "/associations")
        sftp.chmod(REMOTE + "/associations", 0o755)
        sftp.put(str(CACHE / "libzz-lab5-scale.so"), PLUGIN)
    hwmon = f"""[Unit]
Description=Lab 5 emulated CPU inputs via stock phosphor-hwmon
After=xyz.openbmc_project.ObjectMapper.service
[Service]
Environment=LABEL_temp1=p0_core0_temp LABEL_temp2=p1_core0_temp
Environment=WARNLO_temp1=5000 WARNHI_temp1=80000 CRITLO_temp1=0 CRITHI_temp1=90000
Environment=WARNLO_temp2=5000 WARNHI_temp2=80000 CRITLO_temp2=0 CRITHI_temp2=90000
Environment=INTERVAL=250000
ExecStart=/usr/bin/phosphor-hwmon-readd -p {REMOTE}/hwmon0 -i lab5
Restart=on-failure
"""
    associations = f"""[Unit]
Description=Lab 5 CPU sensors chassis associations
After=xyz.openbmc_project.ObjectMapper.service
[Service]
Type=dbus
BusName=xyz.openbmc_project.Lab5.Associations
ExecStart={REMOTE}/associations
Restart=on-failure
"""
    write(client, "/run/systemd/system/lab5-cpu-sensors.service", hwmon)
    write(client, "/run/systemd/system/lab5-associations.service", associations)
    commands = {unit: "hardware " + unit for unit in HARDWARE_UNITS}
    commands.update(POWER_UNITS)
    for unit, command in commands.items():
        config = ("[Service]\nType=oneshot\nRestart=no\nExecStart=\nExecStartPre=\n"
                  f"ExecStartPost=\nExecStart={REMOTE}/board.sh {command}\n")
        write(client, f"/run/systemd/system/{unit}.d/lab5-hardware.conf", config)
    write(client, "/run/systemd/system/phosphor-ipmi-host.service.d/lab5-hardware.conf",
          "[Service]\nEnvironment=LAB5_FIX_STATIC_SENSOR_SCALE=1\n")
    run(client, "systemctl daemon-reload")
    run(client, "systemctl reset-failed", check=False)
    run(client, "systemctl start " + " ".join(SERVICES))
    run(client, "systemctl restart phosphor-ipmi-host.service")
    # On a first boot eth0 can appear after its socket dependency timed out.
    # Start the real LAN+ socket after network readiness, never emulate IPMI.
    run(client, "systemctl start phosphor-ipmi-net@eth0.socket")
    print("Installed QEMU hardware profile: 2 CPU inputs, PSU/FSI/VRM/LPC mailbox model, native IPMI LAN+, Celsius scale fix")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["install", "status", "temperature", "power-fault", "remove"])
    parser.add_argument("--qemu", action="store_true", required=True,
                        help="Explicitly select the local disposable QEMU lab, never a physical BMC")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--cpu0", type=float, default=42)
    parser.add_argument("--cpu1", type=float, default=44)
    parser.add_argument("--fault", choices=["on", "off"], default="off")
    args = parser.parse_args()
    password = os.getenv("BMC_PASSWORD")
    if not password:
        parser.error("Set BMC_PASSWORD")
    known_hosts = ROOT / ".runtime/known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    client = paramiko.SSHClient()
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("127.0.0.1", 2222, username="root", password=password,
                   look_for_keys=False, allow_agent=False, timeout=15)
    client.save_host_keys(str(known_hosts))
    try:
        if args.command == "install":
            install(client, args.build)
        elif args.command == "status":
            print(run(client, "obmcutil state; systemctl is-active " + " ".join(SERVICES)))
            print(run(client, "journalctl -u phosphor-ipmi-host.service -n 15 --no-pager"))
        elif args.command == "temperature":
            import math
            if not all(math.isfinite(x) and -20 <= x <= 120 for x in [args.cpu0, args.cpu1]):
                parser.error("Emulated temperature must be finite and between -20 and 120 Celsius")
            for index, value in enumerate([args.cpu0, args.cpu1], 1):
                # Atomic replacement prevents the poller from reading an empty input.
                path = REMOTE + f"/hwmon0/temp{index}_input"
                write(client, path + ".new", str(round(value * 1000)) + "\n")
                run(client, f"mv {path}.new {path}")
        elif args.command == "power-fault":
            run(client, ("touch " if args.fault == "on" else "rm -f ") + REMOTE + "/fault_power_on")
        elif args.command == "remove":
            state = run(client, "obmcutil state")
            if "HostState.Off" not in state:
                raise RuntimeError("Stop the emulated host before removing the profile")
            run(client, "systemctl stop " + " ".join(SERVICES))
            for unit in [*HARDWARE_UNITS, *POWER_UNITS, "phosphor-ipmi-host.service"]:
                run(client, f"rm -f /run/systemd/system/{unit}.d/lab5-hardware.conf")
            for service in SERVICES:
                run(client, f"rm -f /run/systemd/system/{service}")
            run(client, "systemctl daemon-reload")
            run(client, "rm -f " + PLUGIN)
            run(client, "systemctl restart phosphor-ipmi-host.service")
            print("Removed lab hardware profile; stock hardware services restored")
    finally:
        client.close()


if __name__ == "__main__":
    main()
