FROM python:3.11-slim

RUN pip install uv

WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system -e ".[dev]" 2>/dev/null || uv pip install --system \
    fastapi "uvicorn[standard]" pydantic redis httpx prometheus-client

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 3031
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3031"]
