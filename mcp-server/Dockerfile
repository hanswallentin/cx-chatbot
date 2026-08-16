FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py bookly_client.py server.py ./

ENV CONFIG_PATH=/config.yaml
ENV PYTHONUNBUFFERED=1

EXPOSE 8100

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import socket; socket.create_connection(('localhost', 8100), timeout=3).close()"

CMD ["python", "server.py"]
