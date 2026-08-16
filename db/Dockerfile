FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql seed.py ./

# config.yaml is mounted read-only by docker-compose at /config.yaml.
ENV CONFIG_PATH=/config.yaml
ENV SCHEMA_PATH=/app/schema.sql

CMD ["python", "seed.py"]
