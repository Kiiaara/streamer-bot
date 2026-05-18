FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY admin/requirements.txt /app/admin/requirements.txt
RUN pip install --no-cache-dir -r /app/admin/requirements.txt

COPY shared/ /app/shared/
COPY admin/ /app/admin/

ENV PYTHONPATH=/app
EXPOSE 9000

CMD ["uvicorn", "admin.main:app", "--host", "0.0.0.0", "--port", "9000", "--proxy-headers", "--forwarded-allow-ips=*"]
