FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/mosaika /app/mosaika
COPY prompts /app/prompts
COPY frontend /app/frontend

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "mosaika.main:app", "--host", "0.0.0.0", "--port", "8000"]
