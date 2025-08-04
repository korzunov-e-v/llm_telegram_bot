FROM python:3.12-alpine AS builder

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

FROM python:3.12-alpine AS runtime

ENV VIRTUAL_ENV=/srv/.venv \
    PATH="/srv/.venv/bin:$PATH" \
    PYTHONPATH="/srv"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY src /srv/src

CMD ["python", "/srv/src/main.py"]
