pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        booleanParam(name: 'INJECT_API_FAILURE', defaultValue: false,
                     description: 'Demonstrate a failed API gate using an invalid password')
    }
    environment {
        BMC_URL = 'https://127.0.0.1:2443'
        BMC_USERNAME = 'root'
        BMC_PASSWORD = credentials('openbmc-password')
        BMC_VERIFY_TLS = 'false'
        PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
        REPORTS = 'lab7/artifacts'
    }
    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
                sh '''
                    mkdir -p "$REPORTS/checkout"
                    git rev-parse HEAD > "$REPORTS/checkout/commit.txt"
                    python --version > "$REPORTS/checkout/tools.txt"
                    qemu-system-arm --version >> "$REPORTS/checkout/tools.txt"
                    chromium --version >> "$REPORTS/checkout/tools.txt"
                    chromedriver --version >> "$REPORTS/checkout/tools.txt"
                    pip freeze > "$REPORTS/checkout/packages.txt"
                '''
            }
            post { always { archiveArtifacts artifacts: 'lab7/artifacts/checkout/**', allowEmptyArchive: true } }
        }
        stage('OpenBMC QEMU') {
            steps {
                sh '''
                    mkdir -p "$REPORTS/qemu"
                    python lab7/scripts/start_qemu.py
                    python lab7/setup_qemu_lab.py install --qemu --build > "$REPORTS/qemu/hardware.log" 2>&1
                    python lab7/scripts/check_ready.py
                '''
            }
            post { always { archiveArtifacts artifacts: 'lab7/artifacts/qemu/**', allowEmptyArchive: true } }
        }
        stage('Redfish API') {
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    mkdir -p "$REPORTS/api"
                    if [ "${INJECT_API_FAILURE:-false}" = true ]; then
                        export BMC_PASSWORD='intentionally-invalid-for-ci-gate'
                    fi
                    python -m pytest lab7/tests/api/test_redfish.py -v \
                        --junitxml="$REPORTS/api/junit.xml" 2>&1 | tee "$REPORTS/api/pytest.log"
                '''
            }
            post {
                always {
                    junit testResults: 'lab7/artifacts/api/junit.xml', allowEmptyResults: false
                    archiveArtifacts artifacts: 'lab7/artifacts/api/**', allowEmptyArchive: true
                }
            }
        }
        stage('Selenium Web UI') {
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    mkdir -p "$REPORTS/web"
                    python -m pytest lab7/tests/web -v \
                        --junitxml="$REPORTS/web/junit.xml" 2>&1 | tee "$REPORTS/web/pytest.log"
                '''
            }
            post {
                always {
                    junit testResults: 'lab7/artifacts/web/junit.xml', allowEmptyResults: false
                    archiveArtifacts artifacts: 'lab7/artifacts/web/**', allowEmptyArchive: true
                }
            }
        }
        stage('Locust load') {
            steps { sh 'python lab7/scripts/run_load.py' }
            post {
                always {
                    junit testResults: 'lab7/artifacts/load/junit.xml', allowEmptyResults: false
                    archiveArtifacts artifacts: 'lab7/artifacts/load/**', allowEmptyArchive: true
                }
            }
        }
    }
    post {
        always {
            sh 'python lab7/scripts/stop_qemu.py'
            archiveArtifacts artifacts: 'lab7/artifacts/**', allowEmptyArchive: true, fingerprint: true
        }
    }
}
