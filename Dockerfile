ARG PY_VARIANT=3.8
ARG PY_IMG_VARIANT=slim
ARG POETRY_VARIANT=1.3.1
# `builder-base-python-base` stage is used to build deps + create our virtual environment
FROM python:${PY_VARIANT}-${PY_IMG_VARIANT} as python-base

ARG IMG_VER
ARG BUILD_DATE
ARG APP_NAME=""
ARG OWNER_NAME=""
# https://github.com/opencontainers/image-spec
LABEL org.opencontainers.image.authors="Matthew Lien, Ronnie McGrog" \
      org.opencontainers.image.url="https://github.com/${OWNER_NAME}/${APP_NAME}" \
      org.opencontainers.image.documentation="https://github.com/${OWNER_NAME}/${APP_NAME}/blob/master/README.md" \
      org.opencontainers.image.source="https://github.com/${OWNER_NAME}/${APP_NAME}/blob/master/Dockerfile" \
      org.opencontainers.image.title="${APP_NAME}" \
      org.opencontainers.image.description="The New (auto rotate) Proxy [Finder | Checker | Server]" \
      org.opencontainers.image.version="${IMG_VER}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Turns off buffering for easier container logging 
    PYTHONUNBUFFERED=1 \
    # pip
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    # poetry
    POETRY_VERSION=${POETRY_VARIANT} \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    # make poetry create the virtual environment
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # paths
    PYSETUP_PATH="/opt/pysetup" \
    POETRY_VIRTUALENVS_PATH="/opt/pysetup/.venv"

# this is activate venv, no need `. $POETRY_VIRTUALENVS_PATH/bin/activate`
ENV PATH="$POETRY_HOME/bin:$POETRY_VIRTUALENVS_PATH/bin:$PATH"

FROM python-base as builder-base

RUN export DEBIAN_FRONTEND=noninteractive\
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        # deps for installing poetry
        curl \
        # deps for building python deps
        build-essential

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python - 

WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./
RUN poetry install --without dev

FROM python-base as production
WORKDIR $PYSETUP_PATH
# copy venv too
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH
COPY ./proxybroker proxybroker
EXPOSE 8888
# venv is activated, so all requirements are available
ENTRYPOINT ["python", "-m", "proxybroker"]