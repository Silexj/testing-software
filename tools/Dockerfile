FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends qemu-system-arm && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["qemu-system-arm", "-m", "256", "-M", "romulus-bmc", "-nographic", "-drive", "file=/work/openbmc.mtd,format=raw,if=mtd", "-net", "nic", "-net", "user,hostfwd=tcp::2222-:22,hostfwd=tcp::2443-:443,hostfwd=udp::2623-:623,hostname=qemu"]
