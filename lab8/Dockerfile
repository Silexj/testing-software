FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends qemu-system-arm \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["qemu-system-arm"]
