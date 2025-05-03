FROM python:3.12-slim AS base

# speed-up: uv installer
RUN pip install --no-cache-dir uv

# copy lockfiles first for layer cache
WORKDIR /app
COPY pyproject.toml poetry.lock /app/

# install deps respecting hashes
RUN uv pip install --prod --require-hashes -r poetry.lock

# copy source
COPY . /app

# entrypoint
CMD ["uvicorn", "dealer_flow.rest_service:app", "--host", "0.0.0.0", "--port", "8000"]
