FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY --from=node-runtime /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        fonts-dejavu-core \
        fonts-liberation \
        libreoffice-writer \
        tesseract-ocr \
        tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-linux.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements-linux.txt

COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci \
    && cd frontend \
    && npx playwright install --with-deps chromium \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN npm --prefix frontend run build \
    && chmod +x deploy/start.sh \
    && useradd --create-home --uid 10001 runr \
    && mkdir -p /app/.backend_data /ms-playwright \
    && chown -R runr:runr /app /ms-playwright

USER runr

EXPOSE 8000

CMD ["./deploy/start.sh", "api"]
