# Tag-and-digest pin: tag (`3.14-slim`) is human-readable documentation,
# digest (`sha256:...`) is the immutability anchor. This dual form is the
# pattern recommended by Docker, Snyk, and Anchore for production base
# images - readers can scan the tag at a glance, builders pull the exact
# bits. SonarCloud rule docker:S8431 disagrees and flags this as
# redundant; that finding is intentionally accepted as "won't fix" with
# the rationale documented in PR #199.
#
# Update procedure:
#   docker pull python:3.14-slim
#   docker inspect --format '{{index .RepoDigests 0}}' python:3.14-slim
FROM python:3.14-slim@sha256:5b3879b6f3cb77e712644d50262d05a7c146b7312d784a18eff7ff5462e77033 AS base

# Connects this image to its source repo on GitHub Container Registry.
# Without this label, GHCR cannot link the package to the repo, and the
# workflow's GITHUB_TOKEN gets a 403 Forbidden on first push to a new
# package in the namespace - even with `permissions: packages: write`
# set in the workflow. Per GitHub docs:
# https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
LABEL org.opencontainers.image.source="https://github.com/bluet/proxybroker2"

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Turns off buffering for easier container logging
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

#RUN apt-get update \
#    && apt-get install -y --no-install-recommends gcc libc-dev libffi-dev \
#    && apt-get clean

RUN apt-get update -y &&\
        apt-get upgrade -y &&\
        apt-get autoremove -y --purge &&\
        apt-get clean &&\
        rm -rf /var/lib/lists/*

RUN \
    pip install poetry==2.1.3

FROM base AS builder

WORKDIR /app
COPY poetry.lock pyproject.toml README.md ./
COPY proxybroker proxybroker

RUN apt-get update && \
    apt-get upgrade -y &&\
    apt-get install -y gcc libc-dev libffi-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --without dev
EXPOSE 8888

ENTRYPOINT ["python", "-m", "proxybroker" ]
