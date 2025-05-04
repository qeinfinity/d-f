# Stage 1: Build environment with Poetry to export requirements
FROM python:3.9.6-slim AS builder

# Install poetry - consider pinning the version if needed
RUN pip install poetry==1.8.3

# Set working directory
WORKDIR /app

# Copy only the necessary files for dependency resolution
COPY pyproject.toml poetry.lock ./

# Export dependencies to requirements.txt format
# Use --without-hashes for simplicity, or remove it if your lock file guarantees hashes
# Use --only main if you want to exclude dev dependencies (recommended for final image)
RUN poetry export --only main --format requirements.txt --output requirements.txt --without-hashes

# Stage 2: Final lightweight image using exported requirements
FROM python:3.9.6-slim AS final

# Set working directory
WORKDIR /app

# Copy exported requirements from the builder stage
COPY --from=builder /app/requirements.txt .

# Install dependencies using pip
# Use --no-cache-dir to keep the layer small
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code from the original build context
# Ensure .dockerignore is set up correctly (e.g., ignore .venv, __pycache__)
COPY . /app

# Entrypoint (remains the same)
CMD ["/app/start.sh"]