# Jenkins controller with everything the pipeline needs already on the agent:
# Docker CLI (to build and run the application image), Python (to run pytest
# and Bandit), Node (to build the frontend and run npm audit) and Trivy (to
# scan the built image). Installing them here means the Jenkinsfile stays
# readable and no stage has to bootstrap its own toolchain at runtime.

FROM jenkins/jenkins:lts-jdk21

USER root

# --- Base tooling -----------------------------------------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg lsb-release git \
      python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

# --- Docker CLI + Compose plugin -------------------------------------------
# Only the client. The daemon is the host's, reached through the mounted
# socket, which is why no docker-ce package is installed here.
RUN install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# --- Node 20 ----------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# --- Trivy (image vulnerability scanner) ------------------------------------
RUN curl -fsSL https://aquasecurity.github.io/trivy-repo/deb/public.key \
      | gpg --dearmor -o /usr/share/keyrings/trivy.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" \
      > /etc/apt/sources.list.d/trivy.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends trivy \
 && rm -rf /var/lib/apt/lists/*

# --- sonar-scanner CLI ------------------------------------------------------
ARG SONAR_SCANNER_VERSION=6.2.1.4610
RUN curl -fsSLo /tmp/sonar-scanner.zip \
      "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux-x64.zip" \
 && apt-get update && apt-get install -y --no-install-recommends unzip \
 && unzip -q /tmp/sonar-scanner.zip -d /opt \
 && mv "/opt/sonar-scanner-${SONAR_SCANNER_VERSION}-linux-x64" /opt/sonar-scanner \
 && ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner \
 && rm /tmp/sonar-scanner.zip \
 && rm -rf /var/lib/apt/lists/*

# The jenkins user must be able to talk to the mounted Docker socket. The gid
# is fixed at runtime by the compose file's group_add, so this only needs the
# user to exist in a docker group.
RUN groupadd -f -g 999 docker && usermod -aG docker jenkins

USER jenkins

# Pre-install the plugins the Jenkinsfile depends on, so the controller comes
# up ready instead of needing them picked by hand in the setup wizard.
RUN jenkins-plugin-cli --plugins \
      workflow-aggregator \
      git \
      github \
      docker-workflow \
      pipeline-stage-view \
      junit \
      coverage \
      htmlpublisher \
      sonar \
      credentials-binding \
      timestamper \
      ws-cleanup
