FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VITOXIC_BUNDLE=/bundle \
    VITOXIC_DEVICE=cpu VITOXIC_THREADS=4
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/stage4.txt /app/requirements.txt
RUN pip install --no-cache-dir 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY src /app/src
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
HEALTHCHECK --start-period=180s --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4)"
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
