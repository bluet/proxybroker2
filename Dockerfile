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

# Pull the uv binary from the official image (recommended pattern per
# https://docs.astral.sh/uv/guides/integration/docker/). Same tag+digest
# pinning rationale as the python:3.14-slim base above.
#
# Update procedure:
#   docker pull ghcr.io/astral-sh/uv:0.11.13
#   docker inspect --format '{{index .RepoDigests 0}}' ghcr.io/astral-sh/uv:0.11.13
COPY --from=ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 /uv /uvx /bin/

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Turns off buffering for easier container logging
    PYTHONUNBUFFERED=1 \
    # uv writes .venv to /app/.venv and uses it as the project venv
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    # Don't bake a uv cache layer into the final image
    UV_NO_CACHE=1

RUN apt-get update -y &&\
        apt-get upgrade -y &&\
        apt-get autoremove -y --purge &&\
        apt-get clean &&\
        rm -rf /var/lib/lists/*

FROM base AS builder

WORKDIR /app

# Install build deps for native Python extensions. No `apt-get upgrade`
# here — the base stage already upgraded the system, so re-running just
# adds time without changing state. `--no-install-recommends` keeps the
# image tight by skipping suggested-but-not-required packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc-dev libffi-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install runtime deps from the lockfile WITHOUT the project itself first
# (separate layer = better cache hit rate when only project source changes).
COPY uv.lock pyproject.toml README.md ./
RUN uv sync --locked --no-install-project --no-dev

# Copy source + install the project into the venv (incremental work over
# the cached dependency layer above).
COPY proxybroker proxybroker
RUN uv sync --locked --no-dev

# Make the project venv's binaries available without `uv run` prefix.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8888

ENTRYPOINT ["python", "-m", "proxybroker"]
