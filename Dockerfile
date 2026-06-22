FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# Installs only Flask — the app runs in fallback mode without model weights.
# For HF model support, install requirements-ml.txt and set NL2CLI_GENERATOR=auto.
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV NL2CLI_GENERATOR=fallback
EXPOSE 5000

CMD ["python", "app.py"]
