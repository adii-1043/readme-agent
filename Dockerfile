# Stage 1: Build dependencies
FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies for git and potential C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install 'uv' for lightning-fast package management (standard in 2026)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files
COPY pyproject.toml . 
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Image
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy your application code
COPY ./agents ./agents
COPY ./tools ./tools
COPY ./api ./api
COPY main.py .

# Expose FastAPI port
EXPOSE 8000

# Run the application with Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]