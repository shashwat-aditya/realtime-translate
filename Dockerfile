FROM python:3.12-slim
WORKDIR /app
COPY apps/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/server/ ./apps/server/
COPY apps/web/ ./apps/web/
CMD ["uvicorn", "apps.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
