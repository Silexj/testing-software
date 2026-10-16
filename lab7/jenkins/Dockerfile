FROM jenkins/jenkins:2.580.1-jdk21
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-arm ipmitool chromium chromium-driver python3 python3-venv \
    gcc-arm-linux-gnueabi g++-arm-linux-gnueabi libc6-dev-armel-cross libsystemd-dev \
    && rm -rf /var/lib/apt/lists/*
COPY lab7/requirements.txt /opt/lab7-requirements.txt
RUN python3 -m venv /opt/lab7-venv \
    && /opt/lab7-venv/bin/pip install --no-cache-dir -r /opt/lab7-requirements.txt
COPY lab7/jenkins/plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY lab7/jenkins/init.groovy /usr/share/jenkins/ref/init.groovy.d/lab7.groovy
ENV PATH="/opt/lab7-venv/bin:${PATH}"
USER jenkins
