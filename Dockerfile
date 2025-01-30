FROM python:3.12-slim

WORKDIR /srv

ENV POETRY_CACHE_DIR=/tmp/poetry_cache

COPY pyproject.toml /srv
COPY poetry.lock /srv

RUN --mount=target=/var/lib/apt/lists,type=cache,mode=0777,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,mode=0777,sharing=locked \
    --mount=target=/root/.cache/pypoetry/cache,type=cache,mode=0777,sharing=locked \
    --mount=target=/root/.cache/pip,type=cache,mode=0777,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    pip install poetry==1.8.3 && \
    poetry install --without dev

COPY src /srv/src

ENV PYTHONPATH=$PYTHONPATH:/srv

CMD ["poetry", "run", "python", "/srv/src/main.py"]
