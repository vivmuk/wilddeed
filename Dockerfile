FROM python:3.11-slim

# WeasyPrint runtime deps + fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    fonts-liberation curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/wilddeed
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/wilddeed.py app/wilddeed.py
COPY api/server.py api/server.py
COPY site/ site/

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8080"]
