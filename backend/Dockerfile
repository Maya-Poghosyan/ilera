FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The commit this image was built from, reported by /healthz so a deploy can see its own build serving.
# Declared after the dependency layer so a new commit doesn't invalidate it.
ARG BUILD_SHA=dev
ENV BUILD_SHA=$BUILD_SHA

RUN addgroup --system app && adduser --system --ingroup app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
