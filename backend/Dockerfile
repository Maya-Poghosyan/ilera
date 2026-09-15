FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system app && adduser --system --ingroup app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "if [ -n \"$BAND_AGENTS_JSON\" ]; then printf '%s' \"$BAND_AGENTS_JSON\" > /app/band_agents.json; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
