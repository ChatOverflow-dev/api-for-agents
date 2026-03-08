FROM python:3.13-slim

# --- Optional corporate CA certificate ---
# Place your CA cert at certs/ca-certificate.crt before building.
COPY certs/ /tmp/certs/
RUN if ls /tmp/certs/*.crt 1>/dev/null 2>&1; then \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ && \
        apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
        update-ca-certificates && \
        rm -rf /var/lib/apt/lists/*; \
    fi && rm -rf /tmp/certs
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
# -----------------------------------------

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
