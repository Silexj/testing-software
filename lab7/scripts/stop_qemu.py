"""Stop only the QEMU process whose PID and flash path belong to this workspace."""
import json
import os
from pathlib import Path
import signal
import time

root = Path.cwd()
pidfile = root / '.runtime/qemu.pid'
out = root / os.getenv('REPORTS', 'lab7/artifacts') / 'qemu'
out.mkdir(parents=True, exist_ok=True)
result = {'qemu_stopped': True, 'owned_pid_found': pidfile.exists()}
if pidfile.exists():
    pid = int(pidfile.read_text())
    proc = Path(f'/proc/{pid}/cmdline')
    if proc.exists():
        command = proc.read_bytes()
        if command:
            assert b'qemu-system-arm' in command and str(root / '.runtime/openbmc.mtd').encode() in command
            os.kill(pid, signal.SIGTERM)
            for _ in range(50):
                if not proc.exists() or not proc.read_bytes():
                    break
                time.sleep(.2)
            else:
                os.kill(pid, signal.SIGKILL)
    pidfile.unlink()
(out / 'cleanup.json').write_text(json.dumps(result, indent=2) + '\n')
print('Workspace QEMU cleaned up')
