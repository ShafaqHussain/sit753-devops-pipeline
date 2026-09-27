# Encrypted Chat — DevOps Pipeline (SIT753 7.3HD)

A real-time chat application with end-to-end encryption, delivered through a
seven-stage Jenkins pipeline that builds, tests, analyses, scans, deploys,
releases and monitors it without manual intervention.

The application is the subject; the pipeline is the work. Both live in this
repository, and everything below can be reproduced from a clean clone.

---

## The pipeline

One trigger runs all seven stages. Each is gated: a failure stops the run and
every later stage is skipped, so nothing reaches release unless everything
before it passed.

| Stage | What it does | Tools |
|---|---|---|
| Build | Compiles the React bundle and assembles it with the Flask backend into one versioned image | Docker multi-stage, Node 20, Vite |
| Test | 30 unit and integration tests behind an enforced coverage gate | pytest, pytest-cov, Flask-SocketIO test client |
| Code Quality | Static analysis of Python and JavaScript, fed the real coverage report | SonarCloud, sonar-scanner |
| Security | Image CVEs, Python SAST and frontend advisories; fails on fixable HIGH or CRITICAL | Trivy, Bandit, npm audit |
| Deploy | Starts the image on staging and proves the deployed version matches this build | Docker, HEALTHCHECK, curl |
| Release | Tags the verified commit and image with its semantic version | Git annotated tags, Docker tags |
| Monitoring | Stands up Prometheus and Grafana, then verifies the target is up and alert rules loaded | Prometheus, Grafana, prometheus-flask-exporter |

Version numbers are derived from the build (`1.0.${BUILD_NUMBER}`), injected
into the image, reported by the running container at `/health`, and pushed to
GitHub as a Git tag. A deployed container can therefore always be traced back
to the commit it came from.

---

## Running the application

Requires Docker Desktop. Nothing else.

```bash
git clone https://github.com/ShafaqHussain/sit753-devops-pipeline.git
cd sit753-devops-pipeline
docker compose up -d --build app
```

The app is at `http://localhost:5000`. Register two accounts in a normal
window and a private window (the private key lives in that browser's
`localStorage`, so two tabs share one identity) and send messages between them.

Bring the whole stack up, including monitoring:

```bash
docker compose up -d --build
```

| Service | URL | Notes |
|---|---|---|
| Application | http://localhost:5000 | SPA, REST API and Socket.IO on one origin |
| Health | http://localhost:5000/health | Status and running version |
| Metrics | http://localhost:5000/metrics | Prometheus exposition format |
| Prometheus | http://localhost:9090 | Targets and alert rules |
| Grafana | http://localhost:3001 | admin / admin, dashboard pre-provisioned |

---

## Running the tests

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements-dev.txt
pytest
```

30 tests. Coverage is an enforced gate, not a report: `pytest.ini` sets
`--cov-fail-under=85`, and the suite currently measures 92%. Reports are
written to `backend/htmlcov/`, `backend/coverage.xml` and
`backend/reports/junit.xml`, which is what Jenkins publishes.

The suite covers registration validation, password hashing, JWT issue, decode,
expiry and forgery, the user directory, and the Socket.IO layer end to end:
authenticated handshake, per-recipient fan-out, payload validation, history
replay and presence cleanup.

Two tests are worth naming. `test_server_stores_only_ciphertext` asserts that
what lands in the database is byte-for-byte what the client encrypted.
`test_each_recipient_receives_only_their_own_copy` asserts that one user is
never handed the ciphertext encrypted for another. Together they verify the
security property the project exists to provide.

---

## Running the pipeline

Jenkins runs in Docker, from an image that already carries the Docker CLI,
Python, Node, Trivy, sonar-scanner and the required plugins.

```bash
docker compose -f docker-compose.jenkins.yml up -d --build
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Open `http://localhost:8080`, unlock with that key, and skip plugin
installation since the image is pre-provisioned.

Add two credentials under Manage Jenkins → Credentials → System → Global. The
IDs are referenced literally by the Jenkinsfile and must match exactly:

| ID | Kind | Value |
|---|---|---|
| `github-credentials` | Username with password | GitHub username and a PAT with Contents: Read and write |
| `sonarcloud-token` | Secret text | SonarCloud user token |

Then create a Pipeline job, set Definition to *Pipeline script from SCM*, point
it at this repository on branch `main` with Script Path `Jenkinsfile`, and
build.

Set `sonar.organization` and `sonar.projectKey` in `sonar-project.properties`
to your own SonarCloud values, and disable Automatic Analysis on the SonarCloud
project, otherwise the CI analysis is rejected as a duplicate.

---

## How the encryption works

Each account generates an X25519 keypair in the browser at registration. The
public key is uploaded; the private key is written to that browser's
`localStorage` and never leaves it.

To send a message, the client fetches the public-key directory and encrypts the
plaintext **separately for every recipient**, including itself, using
libsodium's `crypto_box_easy` (X25519 key exchange with XSalsa20-Poly1305
authenticated encryption). One nonce is generated per message and reused across
recipients, which is safe because `crypto_box` derives a distinct shared key per
sender-recipient pair, so each (nonce, key) pair remains unique.

The client emits `{ nonce, ciphertexts: { userId: ciphertext } }` over
Socket.IO. The server stores one `Message` row for the envelope and one
`MessageRecipient` row per ciphertext, and fans out to each connected client
only the copy addressed to it. The server never holds plaintext and has no
column in which to put any.

### Known limitations, by design

Losing the browser's `localStorage` means losing the private key and therefore
all prior messages; the app offers key regeneration, which orphans old history.
This is inherent to end-to-end encryption, not a defect. A user who registers
after a message was sent can never read it, because no ciphertext copy exists
for them. Encryption is per-recipient fan-out suited to a small room, not a
scalable group-key scheme.

---

## Security findings

The Security stage blocked the first build over six HIGH vulnerabilities, all
in pinned dependencies. The most serious was **CVE-2026-48526**, an
authentication bypass through forged JSON Web Tokens in PyJWT 2.9.0, which is
directly relevant here because every authenticated request and every Socket.IO
handshake is validated by that library. Alongside it, **CVE-2026-32597** (PyJWT
accepting unknown `crit` header extensions), **CVE-2024-6221** (Flask-Cors
defaulting `Access-Control-Allow-Private-Network` to true) and
**CVE-2026-48804** (denial of service in python-socketio). All were fixed by
raising the pinned versions in `backend/requirements.txt`, each bump commented
with the CVE it closes.

Two further findings, in `setuptools` and `msgpack`, came from build tooling
bundled in the base image rather than from application code. The Dockerfile now
removes pip, setuptools and wheel from the runtime layer entirely, since a
container that only runs gunicorn does not need a package installer.
`.trivyignore` records those two identifiers with written justification, and
the reporting scan runs with `--ignorefile /dev/null` so archived reports show
every finding while only the gate acts on the triaged set.

---

## Project structure

```
backend/                Flask API, Socket.IO handlers, models, tests
  app.py                App factory, REST routes, /health, /metrics, SPA serving
  auth.py               JWT issue, decode and the token_required decorator
  models.py             User, Message, MessageRecipient
  socketio_events.py    connect, disconnect, send_message, history
  tests/                30 pytest tests
frontend/               React 18 + Vite client
  src/services/         api, socket and libsodium crypto wrappers
monitoring/             Prometheus and Grafana images, config and dashboard
jenkins/                Jenkins controller image
Dockerfile              Multi-stage application image
docker-compose.yml      Application, Prometheus, Grafana
docker-compose.jenkins.yml   Jenkins controller
Jenkinsfile             The seven-stage pipeline
sonar-project.properties     SonarCloud configuration
.trivyignore            Triaged security findings, with justification
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env` for local development. In the
container these arrive as environment variables.

| Variable | Purpose |
|---|---|
| `APP_VERSION` | Injected at build time; reported at `/health` |
| `DATABASE_URL` | SQLAlchemy URL; SQLite on a named volume in the container |
| `JWT_SECRET_KEY` | Signing key for authentication tokens |
| `FLASK_SECRET_KEY` | Flask session secret |
| `FRONTEND_ORIGIN` | Allowed CORS and Socket.IO origins |
| `SOCKETIO_ASYNC_MODE` | `threading` for the dev server, `eventlet` under gunicorn |

Never commit a real `.env`. It is gitignored.
