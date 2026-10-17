FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY issuer.py .
ENV TOKEN_ISSUER_PORT=8081
EXPOSE 8081
CMD ["sh", "-c", "uvicorn issuer:app --host 0.0.0.0 --port ${TOKEN_ISSUER_PORT:-8081}"]
