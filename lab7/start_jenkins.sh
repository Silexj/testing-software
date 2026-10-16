#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=${1:?Usage: bash lab7/start_jenkins.sh /absolute/path/to/romulus.static.mtd}
image=$(realpath "$image")
test -f "$image"
# Secrets are local ignored files, never Docker build arguments or Git contents.
mkdir -p .runtime/lab7/secrets
chmod 700 .runtime/lab7/secrets
if [[ ! -f .runtime/lab7/secrets/admin-password ]]; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > .runtime/lab7/secrets/admin-password
fi
if [[ ! -f .runtime/lab7/secrets/bmc-password ]]; then
    : "${BMC_PASSWORD:?Set BMC_PASSWORD for the lab firmware}"
    printf '%s' "$BMC_PASSWORD" > .runtime/lab7/secrets/bmc-password
fi
chmod 600 .runtime/lab7/secrets/*
docker build -t testing-software-jenkins:lab7 -f lab7/jenkins/Dockerfile .
# Mount only two dedicated secret files and the read-only original firmware.
# Jenkins and its QEMU run as the host user, so those files remain mode 600.
if docker container inspect testing-software-jenkins >/dev/null 2>&1; then
    docker start testing-software-jenkins
else
    docker volume create testing-software-jenkins-home >/dev/null
    docker run -d --name testing-software-jenkins \
        --user "$(id -u):$(id -g)" \
        --shm-size=512m --pids-limit=512 \
        -p 127.0.0.1:8080:8080 \
        -e JAVA_OPTS='-Djenkins.install.runSetupWizard=false -Xms256m -Xmx1024m' \
        -v testing-software-jenkins-home:/var/jenkins_home:z \
        -v "$image:/opt/openbmc/romulus.mtd:ro,z" \
        -v "$PWD/.runtime/lab7/secrets/admin-password:/run/secrets/jenkins-admin-password:ro,z" \
        -v "$PWD/.runtime/lab7/secrets/bmc-password:/run/secrets/bmc-password:ro,z" \
        testing-software-jenkins:lab7
fi
printf 'Jenkins: http://127.0.0.1:8080/ ; user: labadmin\n'
printf 'Admin password file: %s/.runtime/lab7/secrets/admin-password\n' "$PWD"
