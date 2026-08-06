FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "if [ -n \"$BAND_AGENTS_JSON\" ]; then printf '%s' \"$BAND_AGENTS_JSON\" > /app/band_agents.json; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
