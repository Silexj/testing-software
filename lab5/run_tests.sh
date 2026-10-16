#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
# Python from an activated virtual environment, or override PYTHON explicitly.
"${PYTHON:-python3}" -m pytest test_redfish.py -v \
    --junitxml=results/junit.xml "$@" 2>&1 | tee results/pytest.log
