FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask flask-cors gunicorn pg8000
COPY . .
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8080}"]
