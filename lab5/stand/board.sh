#!/bin/sh
# Hardware model for a QEMU BMC without a POWER9 host, VRMs or FSI.
# The stock OpenBMC state managers complete their normal systemd targets.
# This script never writes CurrentHostState/CurrentPowerState or API responses.
set -eu
root=/run/lab5-hardware
operation=${1:?operation required}
value=${2:-}
case "$operation" in
    power)
        case "$value" in
            On)
                if test -e "$root/fault_power_on"; then
                    echo 'Emulated PSU failure: power stays Off' >&2
                    exit 1
                fi
                ;;
            Off) ;;
            *) exit 2 ;;
        esac
        sleep 1
        printf '%s\n' "$value" > "$root/power.state.new"
        mv "$root/power.state.new" "$root/power.state"
        echo "Emulated PSU: $value"
        ;;
    wait)
        attempts=0
        while test "$attempts" -lt 30; do
            test "$(cat "$root/power.state")" != "$value" || exit 0
            sleep 1
            attempts=$((attempts + 1))
        done
        echo "Emulated PSU did not reach $value" >&2
        exit 1
        ;;
    hardware)
        # These production hooks address hardware that is absent in romulus-bmc.
        # A POWER9 SBE may start only after the emulated PSU has reached On.
        if test "$value" = start_host@0.service; then
            test "$(cat "$root/power.state")" = On
        fi
        echo "Emulated board operation: $value"
        ;;
    *) exit 2 ;;
esac
