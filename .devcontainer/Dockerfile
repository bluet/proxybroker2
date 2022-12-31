ARG PY_IMG_VARIANT=3.9-slim
ARG POETRY_VARIANT=1.3.1

FROM python:${PY_IMG_VARIANT}
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID


ENV PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    # pip
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=off \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=${POETRY_VARIANT} \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    # make poetry use gloabal pakages
    # https://github.com/python-poetry/poetry/pull/3209#issuecomment-710678083
    POETRY_VIRTUALENVS_CREATE=false \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    \
    # paths
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/opt/pysetup" 

ENV PATH="$POETRY_HOME/bin:$PATH"

# install systep packages
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    # Remove imagemagick due to https://security-tracker.debian.org/tracker/CVE-2019-10131
    && apt-get purge -y imagemagick imagemagick-6-common \
    && apt-get install --no-install-recommends -y \
    sudo \
    bash \
    curl \
    build-essential \
    python3-dev

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && touch /etc/sudoers.d/$USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# install python package manager and builder
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python - 
    
# copy project requirement files here to ensure they will be cached
# https://github.com/python-poetry/poetry/discussions/1879#discussioncomment-346113
# becouse of docker isolation there is no venv, vscode will mount project catalog to image by himself
WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./
RUN poetry install --no-root --no-ansi 
EXPOSE 8888
