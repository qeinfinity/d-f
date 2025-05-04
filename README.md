# Dealer-Flow Stack

## Prereqs
```bash
# one-time
curl -sSL https://install.python-poetry.org | python3 -
poetry config virtualenvs.in-project true      # keep .venv local
```

## Local dev
```bash
git clone <repo> && cd dealer-flow-stack
poetry install                 # pulls deps
poetry shell                   # enter venv
cp .env.example .env           # edit Redis/ClickHouse creds
python -m dealer_flow          # starts collector + API
```

## Docker (production-like)
```bash
docker build -t dealer-flow .
docker run --env-file .env -p 8000:8000 dealer-flow
```

## Fast install via uv (optional)
```bash
uv pip install -r poetry.lock
```

## Folder map
```
dealer_flow/
  ├── deribit_ws.py
  ├── greek_calc.py
  ├── dealer_net.py
  ├── gamma_flip.py
  ├── vanna_charm_volga.py
  ├── hpp_score.py
  ├── rules.py
  ├── redis_stream.py
  ├── rest_service.py
  ├── __main__.py
```
