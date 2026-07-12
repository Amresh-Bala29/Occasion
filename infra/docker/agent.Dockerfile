# Build context is the repository root.
FROM python:3.13-slim
WORKDIR /app
COPY services/agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/agent ./
# The infra scripts run inside the service root here (see their AGENT_ROOT fallback).
COPY infra/apply-migrations.py infra/seed-demo-data.py ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
