FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask flask-cors gunicorn pg8000
COPY . .
EXPOSE 8080
CMD ["/bin/sh", "start.sh"]
