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

**Deep scan (assumptions & biases):**
Assume Deribit OI proxies total dealer risk—overlooks OTC hedges. Liquidity proxy (spot+perp book depth × ADV) presumes linear price impact; ignores adversarial meta-orders. Threshold heuristics risk anchoring bias: initial $X M may feel “right” but drifts. Model treats dealers as a monolith, ignoring asymmetric hedge tolerances across desks (incentive mismatch). Confirmation bias likely if back-test tuned on 2023–24 bull regime. Availability bias: privileging greeks we can fetch easily (γ, vanna, charm) over harder micro-structure signals (queue-position speed). Recommend periodic reality-checks against CME options to expose hidden flows.
output


```
**Implementation blueprint (no code yet—await MODE:patch):**

1 Data Ingestion  
 • deribit_ws.py – async collector for `public/settlement`, `public/greeks`, `public/open_interest`  
 • spot_ws.py – Binance/OKX perp & spot streams  
 • meta_snap.py – hourly REST fallback + contract-ID roll map  

2 Greek Kernel  
 • greek_calc.py – vectorised BS greeks; stable under σ>300 % using log-moneyness scaling  
 • dealer_net.py – infer dealer sign: `sign = −customer_net_pos`  
 • surface_grid.py – 3-strike × 2-expiry Gaussian smoother  

3 Flow Engine  
 • gamma_flip.py – detect zero-cross, compute Δ  
 • vanna_charm_volga.py – roll-up NGI, VSS, CHL, VOLG  
 • hpp_score.py – HPP = sign(ΔS)·NGI + α·VSS + β·CHL24h; auto-scale α, β by IQR  

4 Scenario Classifier  
 • rules.py – deterministic buckets 1-6; flow / venue ADV adapts thresholds hourly  

5 Persistence & API  
 • redis_stream.py – pub/sub ticks; back-pressure control  
 • rest_service.py – FastAPI for dashboard & model server  

6 Dash Front-End  
 • tiles: Spot vs G-Flip sparkline, NGI/VSS/CHL gauges, HPP meter, heat-map, context strip  
 • Plotly Dash with WebSocket for 1 min refresh; CSS dark-mode  
```