FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    NO_FINANCIAL_SIGNING=1 \
    S3_ENDPOINT=https://s3.cloud.ru \
    S3_REGION=ru-central-1 \
    S3_BUCKET=ito-hermes-mirror \
    CLOUDRU_BASE_URL=https://foundation-models.api.cloud.ru/v1

WORKDIR /app

RUN pip install --no-cache-dir boto3==1.44.6

COPY hermes_ito_8.py /app/hermes_ito_8.py

RUN useradd -m -u 10001 hermes && chown -R hermes /app
USER hermes

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4).status==200 else 1)"

CMD ["python", "/app/hermes_ito_8.py"]
