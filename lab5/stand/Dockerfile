FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc-arm-linux-gnueabi g++-arm-linux-gnueabi libc6-dev-armel-cross libsystemd-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
CMD ["sh", "build.sh"]
