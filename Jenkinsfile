// SIT753 7.3HD - DevOps pipeline for the end-to-end encrypted chat application.
//
// Seven stages: Build, Test, Code Quality, Security, Deploy, Release, Monitoring.
// Every stage runs unattended; nothing here needs a human between steps.
//
// A note on bind mounts. Jenkins runs in a container but talks to the host's
// Docker daemon through a mounted socket, so any -v path is resolved by the
// daemon on the HOST, not inside this workspace. Workspace files therefore
// cannot be bind-mounted into containers the pipeline starts. Everything the
// deployed containers need is baked into images instead, and persistent data
// uses named volumes.

pipeline {
    agent any

    environment {
        APP_NAME       = 'encrypted-chat'
        VERSION        = "1.0.${BUILD_NUMBER}"
        IMAGE          = "encrypted-chat:1.0.${BUILD_NUMBER}"
        PROM_IMAGE     = "encrypted-chat-prometheus:1.0.${BUILD_NUMBER}"
        GRAFANA_IMAGE  = "encrypted-chat-grafana:1.0.${BUILD_NUMBER}"

        STAGING_NAME   = 'encrypted-chat-staging'
        STAGING_PORT   = '5001'
        NETWORK        = 'sit753-net'

        PROM_PORT      = '9090'
        GRAFANA_PORT   = '3001'

        GIT_REPO       = 'github.com/ShafaqHussain/sit753-devops-pipeline.git'
        COVERAGE_GATE  = '85'
    }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    stages {

        // =====================================================================
        // 1. BUILD
        // Compiles the React frontend and assembles it with the Flask backend
        // into a single versioned image. The version is injected as a build
        // arg so the running container can report it at /health, which is what
        // makes a deployed container traceable back to this build and, via the
        // Release stage, to a Git tag.
        // =====================================================================
        stage('Build') {
            steps {
                sh '''
                    set -e
                    echo "Building ${IMAGE}"
                    docker build \
                        --build-arg APP_VERSION=${VERSION} \
                        -t ${IMAGE} \
                        -t ${APP_NAME}:latest \
                        .
                '''
                sh '''
                    set -e
                    mkdir -p reports
                    {
                        echo "version=${VERSION}"
                        echo "image=${IMAGE}"
                        echo "commit=$(git rev-parse HEAD)"
                        echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                        echo "image_id=$(docker image inspect ${IMAGE} --format '{{.Id}}')"
                        echo "image_size_bytes=$(docker image inspect ${IMAGE} --format '{{.Size}}')"
                    } > reports/build-info.txt
                    cat reports/build-info.txt
                '''
            }
            post {
                success {
                    archiveArtifacts artifacts: 'reports/build-info.txt', fingerprint: true
                }
            }
        }

        // =====================================================================
        // 2. TEST
        // Unit and integration tests. The socket tests drive the real
        // Flask-SocketIO handlers through a test client, so the authentication
        // handshake is covered, not just the REST surface. pytest.ini carries
        // --cov-fail-under, so a coverage drop fails this stage and therefore
        // the build.
        // =====================================================================
        stage('Test') {
            steps {
                sh '''
                    set -e
                    cd backend
                    python3 -m venv .venv
                    .venv/bin/pip install --quiet --upgrade pip
                    .venv/bin/pip install --quiet -r requirements-dev.txt
                    .venv/bin/pytest
                '''
            }
            post {
                always {
                    junit testResults: 'backend/reports/junit.xml', allowEmptyResults: false
                    recordCoverage(
                        tools: [[parser: 'COBERTURA', pattern: 'backend/coverage.xml']],
                        sourceDirectories: [[path: 'backend']],
                        qualityGates: [
                            [threshold: 85.0, metric: 'LINE', baseline: 'PROJECT', criticality: 'FAILURE']
                        ]
                    )
                    publishHTML(target: [
                        reportDir: 'backend/htmlcov',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report',
                        keepAll: true,
                        alwaysLinkToLastBuild: true,
                        allowMissing: false
                    ])
                }
            }
        }

        // =====================================================================
        // 3. CODE QUALITY
        // SonarCloud analyses both languages in the repo: Python on the server
        // and JavaScript on the client. The coverage report from the Test stage
        // is handed over so Sonar reports on real coverage rather than
        // guessing. The build fails if the project's quality gate fails.
        // =====================================================================
        stage('Code Quality') {
            steps {
                withCredentials([string(credentialsId: 'sonarcloud-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        set -e
                        sonar-scanner \
                          -Dsonar.token=${SONAR_TOKEN} \
                          -Dsonar.projectVersion=${VERSION} \
                          -Dsonar.scm.revision=$(git rev-parse HEAD)
                    '''
                }
            }
        }

        // =====================================================================
        // 4. SECURITY
        // Three complementary scans, because they catch different things:
        //   Trivy  - known CVEs in OS packages and Python wheels inside the
        //            built image. Gates the build on HIGH and CRITICAL.
        //   Bandit - static analysis of our own Python for insecure patterns
        //            (hardcoded secrets, weak crypto, unsafe deserialisation).
        //   npm audit - known advisories in the frontend dependency tree.
        // Reports are archived whether or not the gate trips, so findings can
        // be discussed in the report rather than just blocking silently.
        // =====================================================================
        stage('Security') {
            steps {
                sh '''
                    set -e
                    mkdir -p reports

                    echo "--- Trivy: image vulnerability scan ---"
                    trivy image --scanners vuln --format json \
                        -o reports/trivy-report.json ${IMAGE} || true
                    trivy image --scanners vuln --format table ${IMAGE} \
                        | tee reports/trivy-report.txt || true

                    echo "--- Bandit: Python static analysis ---"
                    cd backend
                    .venv/bin/bandit -r . \
                        -x ./tests,./.venv \
                        -f json -o ../reports/bandit-report.json || true
                    .venv/bin/bandit -r . \
                        -x ./tests,./.venv \
                        -f txt | tee ../reports/bandit-report.txt || true
                    cd ..

                    echo "--- npm audit: frontend dependencies ---"
                    cd frontend
                    npm audit --json > ../reports/npm-audit.json || true
                    npm audit || true
                    cd ..
                '''
                // The gate is a separate step so the reports above always exist
                // before a failure can stop the stage.
                sh '''
                    set -e
                    echo "--- Enforcing gate: no HIGH or CRITICAL CVEs ---"
                    trivy image --scanners vuln \
                        --severity HIGH,CRITICAL \
                        --ignore-unfixed \
                        --exit-code 1 \
                        ${IMAGE}
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/*', allowEmptyArchive: true, fingerprint: true
                }
            }
        }

        // =====================================================================
        // 5. DEPLOY
        // Replaces the staging container with the image built above, then waits
        // for Docker to report it healthy and proves the deployment by calling
        // /health and checking the version it reports matches this build. A
        // container that starts but serves the wrong build is a failed deploy,
        // not a successful one.
        // =====================================================================
        stage('Deploy') {
            steps {
                sh '''
                    set -e
                    docker network inspect ${NETWORK} >/dev/null 2>&1 \
                        || docker network create ${NETWORK}

                    docker rm -f ${STAGING_NAME} >/dev/null 2>&1 || true

                    docker run -d \
                        --name ${STAGING_NAME} \
                        --network ${NETWORK} \
                        -p ${STAGING_PORT}:5000 \
                        -e APP_VERSION=${VERSION} \
                        -e DATABASE_URL=sqlite:////app/data/chat.db \
                        -e JWT_SECRET_KEY=staging-jwt-secret-${BUILD_NUMBER} \
                        -e FLASK_SECRET_KEY=staging-flask-secret-${BUILD_NUMBER} \
                        -e FRONTEND_ORIGIN='*' \
                        -e SOCKETIO_ASYNC_MODE=eventlet \
                        -v chat-staging-data:/app/data \
                        --restart unless-stopped \
                        ${IMAGE}
                '''
                sh '''
                    set -e
                    echo "Waiting for ${STAGING_NAME} to report healthy..."
                    for i in $(seq 1 30); do
                        STATUS=$(docker inspect --format '{{.State.Health.Status}}' ${STAGING_NAME} 2>/dev/null || echo starting)
                        echo "  attempt $i: ${STATUS}"
                        if [ "${STATUS}" = "healthy" ]; then break; fi
                        if [ "${STATUS}" = "unhealthy" ]; then
                            docker logs ${STAGING_NAME}
                            echo "Container went unhealthy"; exit 1
                        fi
                        sleep 3
                    done
                    [ "${STATUS}" = "healthy" ] || { docker logs ${STAGING_NAME}; exit 1; }
                '''
                sh '''
                    set -e
                    echo "--- Smoke test: /health from inside the network ---"
                    BODY=$(docker run --rm --network ${NETWORK} curlimages/curl:8.10.1 \
                        -fsS http://${STAGING_NAME}:5000/health)
                    echo "${BODY}"

                    echo "${BODY}" | grep -q '"status": *"ok"' \
                        || { echo "health did not report ok"; exit 1; }
                    echo "${BODY}" | grep -q "\\"version\\": *\\"${VERSION}\\"" \
                        || { echo "deployed version is not ${VERSION}"; exit 1; }

                    echo "--- Smoke test: SPA is served ---"
                    docker run --rm --network ${NETWORK} curlimages/curl:8.10.1 \
                        -fsS http://${STAGING_NAME}:5000/ | grep -qi '<div id="root"' \
                        || { echo "frontend bundle not served"; exit 1; }

                    echo "Deployment verified: ${VERSION} live on port ${STAGING_PORT}"
                '''
            }
        }

        // =====================================================================
        // 6. RELEASE
        // Promotes the verified build by tagging the exact commit with its
        // semantic version and pushing that tag to GitHub, and by tagging the
        // image as the current release. Only reached when Deploy has proved the
        // build healthy, so a tag always points at something that ran.
        // =====================================================================
        stage('Release') {
            steps {
                sh '''
                    set -e
                    docker tag ${IMAGE} ${APP_NAME}:release
                    docker tag ${IMAGE} ${APP_NAME}:stable
                '''
                withCredentials([usernamePassword(
                    credentialsId: 'github-credentials',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN'
                )]) {
                    sh '''
                        set -e
                        # Authorship is set explicitly so release tags are
                        # attributed to the project owner rather than to
                        # whatever identity the build host happens to carry.
                        git config user.name  "Syed Shafaq Hussain"
                        git config user.email "shafaqhussain04@gmail.com"

                        TAG="v${VERSION}"

                        if git rev-parse "${TAG}" >/dev/null 2>&1; then
                            echo "Tag ${TAG} already exists locally, skipping"
                        else
                            git tag -a "${TAG}" -m "Release ${TAG} (build #${BUILD_NUMBER})"
                        fi

                        git push "https://${GIT_USER}:${GIT_TOKEN}@${GIT_REPO}" "${TAG}"
                        echo "Released ${TAG}"
                    '''
                }
                sh '''
                    set -e
                    mkdir -p reports
                    {
                        echo "release_tag=v${VERSION}"
                        echo "image=${IMAGE}"
                        echo "commit=$(git rev-parse HEAD)"
                        echo "released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                    } > reports/release-info.txt
                '''
                archiveArtifacts artifacts: 'reports/release-info.txt', fingerprint: true
            }
        }

        // =====================================================================
        // 7. MONITORING
        // Brings up Prometheus (scraping the app's /metrics) and Grafana with a
        // provisioned datasource and dashboard, then verifies the pipeline has
        // actually produced working observability rather than merely starting
        // two containers: the scrape target must be UP and the alerting rules
        // must be loaded.
        // =====================================================================
        stage('Monitoring') {
            steps {
                sh '''
                    set -e
                    docker build -t ${PROM_IMAGE}    -f monitoring/Dockerfile.prometheus monitoring
                    docker build -t ${GRAFANA_IMAGE} -f monitoring/Dockerfile.grafana    monitoring

                    docker rm -f chat-prometheus chat-grafana >/dev/null 2>&1 || true

                    docker run -d --name chat-prometheus \
                        --network ${NETWORK} \
                        -p ${PROM_PORT}:9090 \
                        --restart unless-stopped \
                        ${PROM_IMAGE}

                    docker run -d --name chat-grafana \
                        --network ${NETWORK} \
                        -p ${GRAFANA_PORT}:3000 \
                        -e GF_SECURITY_ADMIN_USER=admin \
                        -e GF_SECURITY_ADMIN_PASSWORD=admin \
                        -e GF_AUTH_ANONYMOUS_ENABLED=true \
                        -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
                        --restart unless-stopped \
                        ${GRAFANA_IMAGE}
                '''
                sh '''
                    set -e
                    echo "--- Verifying Prometheus is scraping the application ---"
                    for i in $(seq 1 20); do
                        TARGETS=$(docker run --rm --network ${NETWORK} curlimages/curl:8.10.1 \
                            -fsS "http://chat-prometheus:9090/api/v1/targets?state=active" 2>/dev/null || echo "")
                        echo "${TARGETS}" | grep -q '"health":"up"' && break
                        echo "  attempt $i: target not up yet"
                        sleep 5
                    done
                    echo "${TARGETS}" | grep -q '"health":"up"' \
                        || { echo "Prometheus never reported the app target as up"; exit 1; }
                    echo "Scrape target is UP"
                '''
                sh '''
                    set -e
                    echo "--- Verifying alerting rules are loaded ---"
                    RULES=$(docker run --rm --network ${NETWORK} curlimages/curl:8.10.1 \
                        -fsS "http://chat-prometheus:9090/api/v1/rules")
                    for RULE in ApplicationDown HighServerErrorRate SlowResponseTime; do
                        echo "${RULES}" | grep -q "${RULE}" \
                            || { echo "Alert rule ${RULE} is not loaded"; exit 1; }
                        echo "  ${RULE} loaded"
                    done

                    mkdir -p reports
                    echo "${RULES}" > reports/prometheus-rules.json
                    echo "Monitoring verified. Prometheus :${PROM_PORT}, Grafana :${GRAFANA_PORT}"
                '''
                archiveArtifacts artifacts: 'reports/prometheus-rules.json', allowEmptyArchive: true
            }
        }
    }

    post {
        success {
            echo """
            =====================================================
            Pipeline SUCCEEDED - ${APP_NAME} ${VERSION}
            -----------------------------------------------------
            Application : http://localhost:${STAGING_PORT}
            Prometheus  : http://localhost:${PROM_PORT}
            Grafana     : http://localhost:${GRAFANA_PORT} (admin/admin)
            Release tag : v${VERSION}
            =====================================================
            """
        }
        failure {
            sh 'docker logs ${STAGING_NAME} --tail 100 2>/dev/null || true'
            echo "Pipeline FAILED at build ${BUILD_NUMBER}. See the stage view for which stage stopped it."
        }
        always {
            sh 'docker image prune -f --filter "until=168h" >/dev/null 2>&1 || true'
        }
    }
}
