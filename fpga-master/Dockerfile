FROM python:3.11-slim

RUN pip install uv

WORKDIR /app

# Install dependencies via uv
RUN uv pip install --system \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.29" \
    "pydantic>=2.0" \
    "redis>=5.0" \
    "httpx>=0.27" \
    "prometheus-client>=0.20"

COPY . .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 3030
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3030"]
