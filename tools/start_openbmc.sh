#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=${1:?Usage: bash tools/start_openbmc.sh /path/to/romulus.static.mtd}
test -f "$image"
mkdir -p .runtime
if [[ ! -f .runtime/openbmc.mtd ]]; then
    cp --reflink=auto "$image" .runtime/openbmc.mtd
fi
docker build -t testing-software-qemu tools
if docker container inspect testing-software-openbmc >/dev/null 2>&1; then
    docker start testing-software-openbmc
else
    docker run -d --name testing-software-openbmc \
        -p 127.0.0.1:2222:2222 -p 127.0.0.1:2443:2443 \
        -p 127.0.0.1:2623:2623/udp \
        -v "$PWD/.runtime:/work:z" testing-software-qemu
fi
