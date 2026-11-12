FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY spotify_ingest ./spotify_ingest

CMD ["python", "-m", "spotify_ingest.run", "--loop"]
