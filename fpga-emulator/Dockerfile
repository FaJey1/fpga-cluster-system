FROM python:3.11-slim

RUN pip install uv

WORKDIR /app
RUN uv pip install --system fastapi "uvicorn[standard]" pydantic prometheus-client

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 4000
CMD ["uvicorn", "fpga_emulator.main:app", "--host", "0.0.0.0", "--port", "4000"]
