FROM python:3.12-slim AS builder

WORKDIR /srv

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY pyproject.toml /srv
COPY poetry.lock /srv

RUN --mount=target=/var/lib/apt/lists,type=cache,mode=0777,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,mode=0777,sharing=locked \
    --mount=target=/root/.cache/pypoetry/cache,type=cache,mode=0777,sharing=locked \
    --mount=target=/root/.cache/pip,type=cache,mode=0777,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    pip install poetry==1.8.3 && \
    poetry install --without dev




FROM python:3.12-slim AS runtime

ENV VIRTUAL_ENV=/srv/.venv \
    PATH="/srv/.venv/bin:$PATH" \
    PYTHONPATH="$PYTHONPATH:/srv"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY src /srv/src

CMD ["python", "/srv/src/main.py"]
