# Image for the "Try it" demo: docker compose --profile demo up --build
# It holds Python and the server's packages only. The project folder is mounted at /app (see docker-compose.yml),
# so the code that runs is the code in this checkout. Not meant for a real deployment: see docs/DEPLOYMENT.md.
FROM python:3.13-slim

# socat passes the published port to the server's own loopback address (scripts/docker_demo.py says why)
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
EXPOSE 8000
CMD ["python", "scripts/docker_demo.py"]
