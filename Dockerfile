# Imagem única do estúdio: o mesmo arquivo serve o "web" e, depois, o "trabalhador".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# pg_dump 16 (mesma versão do banco) para o backup diário, do repositório oficial do Postgres.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
ENV PG_DUMP=/usr/lib/postgresql/16/bin/pg_dump

WORKDIR /app

# Dependências primeiro (cache), sem as de desenvolvimento.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Modelos do medidor de rosto (OpenCV Zoo: YuNet MIT, SFace Apache-2.0), baixados no build.
ENV MEDIDOR_MODELOS=/app/modelos
RUN mkdir -p /app/modelos \
    && python -c "import urllib.request as u; b='https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/'; [u.urlretrieve(b + s, '/app/modelos/' + n) for n, s in (('yunet.onnx', 'face_detection_yunet/face_detection_yunet_2023mar.onnx'), ('sface.onnx', 'face_recognition_sface/face_recognition_sface_2021dec.onnx'))]"

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# Usuário sem privilégios.
RUN useradd --create-home --uid 1000 estudio
USER estudio

ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
