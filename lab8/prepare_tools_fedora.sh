#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .runtime/lab8/packages .runtime/lab8/binroot
# Download official Fedora packages locally; no system package or sysctl changes.
dnf --repo=fedora --repo=updates \
    --setopt=cachedir="$PWD/.runtime/lab8/dnf-cache" \
    --setopt=logdir="$PWD/.runtime/lab8/dnf-logs" \
    download --destdir .runtime/lab8/packages perf nmon
for lab8_package in .runtime/lab8/packages/*.rpm; do
    rpm2cpio "$lab8_package" | (cd .runtime/lab8/binroot && \
        cpio -idmu --quiet --no-absolute-filenames './usr/bin/perf' './usr/bin/nmon')
done
.runtime/lab8/binroot/usr/bin/perf --version
printf 'Tools directory: %s/.runtime/lab8/binroot/usr/bin\n' "$PWD"
