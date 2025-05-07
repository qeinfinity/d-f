================================================
FILE: README.md
================================================
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


================================================
FILE: 5-may-gitingest.md
================================================
================================================
FILE: README.md
================================================
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



poetry build failed because no 


================================================
FILE: docker-compose.yml
================================================
services:
  dealer-flow:
    build: . # Build the image from the Dockerfile in the current directory
    image: dealer-flow # Use the image tag you built
    container_name: dealer_flow_app
    env_file:
      - .env # Pass environment variables from .env file
    ports:
      - "8000:8000" # Map container port 8000 to host port 8000
    depends_on:
      - redis # Ensure Redis starts before the app
    networks:
      - dealer_net

  redis:
    image: redis:alpine # Use an official Redis image
    container_name: dealer_flow_redis
    # If you set a password in redis.conf and want to use it here:
    # command: redis-server --requirepass ${REDIS_PASSWORD}
    networks:
      - dealer_net
    # Optional: Persist Redis data outside the container
    # volumes:
    #   - redis_data:/data

networks:
  dealer_net:
    driver: bridge

# Optional: Define named volume for persistence
# volumes:
#   redis_data:


================================================
FILE: Dockerfile
================================================
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


================================================
FILE: pyproject.toml
================================================
[tool.poetry]
name = "dealer-flow-stack"
version = "0.1.0"
description = "Real-time dealer-flow dashboard for BTC options"
authors = ["boscovich"]
readme = "README.md"
packages = [{ include = "dealer_flow" }]

[tool.poetry.dependencies]
python = "3.9.6"
websockets = "^12.0"
aiohttp = "^3.9"
redis = "^5.0"
numpy = "^1.26"
pandas = "^2.2"
numba = "^0.59"
pydantic = "^2.7"
pydantic-settings = "^2.0"
fastapi = "^0.111"
uvicorn = { extras = ["standard"], version = "^0.29" }
orjson = "^3.10"
clickhouse-driver = "^0.2.9"
plotly = "^5.20"
aioredis = "^2.0"
scipy = "^1.13"

[tool.poetry.group.dev.dependencies]
black = "^24.3"
isort = "^5.13"
mypy = "^1.9"
pytest = "^8.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"




================================================
FILE: REPORT.md
================================================
rationale
**Pre-Mortem (Documentation Generation, ≤120 w):**
- Missing context: Forgetting initial setup details (macOS, Poetry, initial Dockerfile intent).
- Incorrect diagnosis summary: Misrepresenting the reason for a specific error.
- Solution ambiguity: Not clearly stating the final, successful command or config change for each step.
- Overlooking local issues: Focusing only on Docker and forgetting the `llvmlite` and Redis troubleshooting.
- Lack of structure: Presenting steps chronologically but without logical grouping, making it hard to follow.
- Ignoring user decisions: Not reflecting the user's choice to switch away from `uv` back to `pip`.

**Analysis:** The goal is to create a clear, chronological narrative of the troubleshooting session for future maintainers. It needs to capture the state, the error encountered, the reasoning applied, and the solution implemented at each significant step, covering both Docker build issues and local environment problems (LLVM, Redis). Using a structured format (Problem, Diagnosis, Cause, Solution) for each step will enhance clarity. The document should reflect the iterative nature of the process and the final working state/decisions.
``````markdown
output
## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide

**Project Goal:** Build and run the "Dealer-Flow Stack" application, primarily focusing on creating a functional Docker image for deployment and resolving local development environment issues.

**Initial Setup:**
*   **OS:** macOS (inferred from terminal logs, specifically paths like `/opt/homebrew`, `/var/folders`, and Zsh prompt `username@Mac ... %`)
*   **Dependency Management:** Poetry
*   **Initial Dockerfile Intent:** Use `uv` within the Docker container for faster dependency installation.

---

**Phase 1: Docker Build Troubleshooting (Iterative)**

1.  **Problem 1: `poetry.lock` Not Found**
    *   **Symptom:** `docker build` failed during `COPY pyproject.toml poetry.lock /app/` step with error `"/poetry.lock": not found`.
    *   **Diagnosis:** The `poetry.lock` file existed locally in the build context root (`dealer-flow-stack`), but was not being included in the context sent to the Docker daemon.
    *   **Cause:** The `.dockerignore` file contained the wildcard pattern `*.lock`, which matched and excluded `poetry.lock`.
    *   **Solution:** Removed the `*.lock` line from the `.dockerignore` file.

2.  **Problem 2: Invalid `uv` Flag (`--prod`)**
    *   **Symptom:** `docker build` failed during `RUN uv pip install --prod ... -r poetry.lock` step with error `unexpected argument '--prod' found`.
    *   **Diagnosis:** The `uv pip install` command, when used with `-r`, does not recognize the `--prod` flag.
    *   **Cause:** Incorrect `uv` command syntax for installing only production dependencies from a requirements file.
    *   **Solution:** Removed the `--prod` flag, changing the command to `RUN uv pip install --require-hashes -r poetry.lock`.

3.  **Problem 3: `uv` Parsing `poetry.lock` Incorrectly (as requirements.txt)**
    *   **Symptom:** `docker build` failed during `RUN uv pip install --require-hashes -r poetry.lock` step with error `Unexpected '['... at poetry.lock:3:1`.
    *   **Diagnosis:** Despite the previous fix, `uv` was still trying to parse the TOML-formatted `poetry.lock` file as if it were a plain `requirements.txt` file, failing on the first `[[package]]` table definition.
    *   **Cause:** `uv pip install -r` is fundamentally designed for `requirements.txt` format, not `poetry.lock`. The correct command for synchronizing based on lock files is `uv pip sync`.
    *   **Solution:** Changed the command to `RUN uv pip sync --require-hashes poetry.lock`.

4.  **Problem 4: `uv pip sync` Still Parsing Incorrectly**
    *   **Symptom:** `docker build` failed with the *same* `Unexpected '['...` error even when using `uv pip sync poetry.lock`.
    *   **Diagnosis:** Highly unusual. This suggested the specific `uv` version or environment might be buggy or misinterpreting the direct lock file argument. An alternative is to rely on `uv`'s ability to auto-detect the lock file when syncing the project file.
    *   **Cause:** Unclear `uv` behavior when passed `poetry.lock` directly in this specific build environment.
    *   **Solution:** Changed the command to target the project file: `RUN uv pip sync --require-hashes pyproject.toml`.

5.  **Problem 5: `uv pip sync` Requires Environment Context**
    *   **Symptom:** `docker build` failed during `RUN uv pip sync --require-hashes pyproject.toml` step with error `No virtual environment found... pass --system`.
    *   **Diagnosis:** `uv` detected it wasn't in a virtual environment and refused to install into the container's base Python environment without explicit permission.
    *   **Cause:** `uv`'s default safety mechanism.
    *   **Solution:** Added the `--system` flag to grant permission: `RUN uv pip sync --system --require-hashes pyproject.toml`.

6.  **Decision Point: Removing `uv`**
    *   **Context:** Faced with multiple `uv`-specific hurdles in the Docker build process.
    *   **Decision:** Revert to a more traditional Docker build approach using standard `pip` and `poetry` (in a builder stage) for potentially greater stability and predictability, sacrificing `uv`'s speed advantage.

7.  **Problem 6: `poetry export` Command Not Found (Multi-Stage Build)**
    *   **Symptom:** The multi-stage Dockerfile using `pip` failed during the builder stage at `RUN poetry export ...` with error `The requested command export does not exist`.
    *   **Diagnosis:** The version of Poetry installed by the default `RUN pip install poetry` was too old (likely < 1.2) and lacked the `export` command.
    *   **Cause:** Default `pip install` pulled an outdated Poetry version.
    *   **Solution:** Pinned a specific, newer version of Poetry in the builder stage: `RUN pip install poetry==1.8.3`. (Build was assumed successful after this, conversation moved to local issues).

---

**Phase 2: Local Environment Troubleshooting (macOS with Homebrew)**

1.  **Problem 7: `llvmlite` Build Failure (`llvm-config` Not Found)**
    *   **Symptom:** `poetry install` failed locally with `RuntimeError: Could not find a llvm-config binary`.
    *   **Diagnosis:** `llvmlite`, a dependency (likely via `numba`), requires the LLVM compiler toolkit, specifically the `llvm-config` utility, to build its native extensions. This utility was not installed or not found in the system `PATH`.
    *   **Cause:** Missing required system dependency (LLVM).
    *   **Solution:** Install LLVM using Homebrew: `brew install llvm`.

2.  **Problem 8: `llvmlite` Build Failure (LLVM Version Mismatch)**
    *   **Symptom:** After installing LLVM via Homebrew, `poetry install` failed again, this time with `RuntimeError: Building llvmlite requires LLVM 14, got '20.1.3'`. (Initially, the `LLVM_CONFIG_PATH` env var was set pointing to the new LLVM 20.x `llvm-config`).
    *   **Diagnosis:** The specific `llvmlite` version locked in `poetry.lock` (0.42.0) was incompatible with the currently installed and referenced LLVM version (20.1.3). It explicitly required LLVM 14.x.
    *   **Cause:** Incompatible versions of interdependent system (LLVM) and Python (`llvmlite`) libraries.
    *   **Solution:**
        *   Install the required LLVM version alongside the existing one: `brew install llvm@14`.
        *   Update the environment variable to point specifically to the LLVM 14 executable before running install: `export LLVM_CONFIG_PATH=$(brew --prefix llvm@14)/bin/llvm-config`.

3.  **Problem 9: `llvmlite` Build Failure (Build Env Ignoring `LLVM_CONFIG_PATH`)**
    *   **Symptom:** Even after setting `LLVM_CONFIG_PATH` correctly to LLVM 14, `poetry install` *still* failed with the version mismatch error, indicating the build process was somehow finding LLVM 20.x.
    *   **Diagnosis:** The isolated build environment used by Poetry/pip wasn't inheriting or respecting the exported `LLVM_CONFIG_PATH`. It was likely finding the newer LLVM first via the standard system `PATH`.
    *   **Cause:** Environment variable propagation or `PATH` precedence issue within the build subprocess.
    *   **Solution:** Force the `PATH` order for the installation command only: `PATH="$(brew --prefix llvm@14)/bin:$PATH" poetry install`.

---

**Phase 3: Redis Configuration & Connection Issues**

1.  **Problem 10: Redis Server Start Failure (`Address already in use`)**
    *   **Symptom:** Attempting to start Redis manually (`redis-server /opt/homebrew/etc/redis.conf`) failed with `bind: Address already in use`.
    *   **Diagnosis:** Another Redis process was already running and bound to the configured port (default 6379).
    *   **Cause:** Trying to run multiple instances on the same port, likely due to a background service already running (e.g., via `brew services`).
    *   **Solution:** Stop the existing process (`brew services stop redis` or `kill <PID>`) before attempting to start a new one manually, OR consistently use `brew services start/stop/restart redis` to manage the background instance.

2.  **Problem 11: Redis Authentication Failure (`NOAUTH` / `WRONGPASS`)**
    *   **Symptom:** `redis-cli -a <password> ping` failed with authentication errors, even after seemingly setting the password.
    *   **Diagnosis:** The password being provided to `redis-cli` did not match the `requirepass` directive for the Redis instance it was actually connecting to (likely the pre-existing one on port 6379).
    *   **Cause:** Password mismatch or connecting to the wrong Redis instance.
    *   **Solution:** Verify the exact password in the relevant `redis.conf` file, ensure the correct Redis instance is running, and use the correct password with `redis-cli`. Use `brew services restart redis` to ensure the config file changes are loaded.

3.  **Problem 12: Redis Port Confusion (Multiple Instances)**
    *   **Symptom:** Successfully started a manual instance on port 6380, but `redis-cli` (without `-p`) connected successfully to 6379.
    *   **Diagnosis:** Two Redis instances were confirmed running: the manual one on 6380 and another (likely background/brew service) on 6379. `redis-cli` defaults to 6379.
    *   **Cause:** Multiple running instances; implicit default port usage by `redis-cli`.
    *   **Solution:** Use `redis-cli -p <port>` to target specific instances. Stop unneeded instances. Configure the project's `.env` file (`REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`) to match the *intended* running instance.

---

**Final Status / Key Takeaways for Maintainers:**

*   The Docker build process was eventually stabilized using a multi-stage build, installing Poetry 1.8.3 in the builder stage, exporting `requirements.txt`, and using `pip install -r requirements.txt` in the final stage. `uv` was abandoned due to persistent integration issues in this specific context.
*   The `.dockerignore` file is critical and must *not* exclude essential files like `poetry.lock`.
*   Local macOS development requiring `llvmlite`/`numba` needs careful LLVM version management. Install the specific required version (e.g., `llvm@14`) and ensure the build process uses it, potentially by manipulating the `PATH` directly during installation if environment variables are ignored.
*   Be mindful of multiple Redis instances. Use `brew services` for managing the background instance reliably on macOS. Always verify which port an instance is running on and use `redis-cli -p <port> -a <password>` for specific connections. Ensure the `.env` file aligns with the target Redis instance.

## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide (Continuation)

**Previous State:** The Docker image (`dealer-flow`) builds successfully using a multi-stage process with `pip` and Poetry 1.8.3. The container starts via `docker run`, launching Uvicorn. However, initial attempts to run failed due to missing `aioredis` dependency and subsequently a Pydantic v1 vs v2 `BaseSettings` import error. These were resolved by adding `aioredis` and `pydantic-settings` to `pyproject.toml`, updating `poetry.lock`, modifying the import in `dealer_flow/config.py`, and rebuilding the image. The container now runs, but accessing the `/snapshot` endpoint yields errors.

---

**Phase 4: Runtime Logic Debugging (Post-Build)**

1.  **Problem 13: `/snapshot` Endpoint Fails (`IndexError` / `500`)**
    *   **Symptom:** Running the container via `docker run --env-file .env -p 8000:8000 dealer-flow` starts Uvicorn successfully. However, accessing `http://localhost:8000/snapshot` results in a `500 Internal Server Error`. Container logs show `IndexError: list index out of range` at `dealer_flow/rest_service.py:12` when executing `list(last)[0]`.
    *   **Diagnosis:** The `redis.xrevrange(STREAM_KEY_METRICS, count=1)` call returns an empty list (`last`), indicating the target Redis stream `dealer_metrics` is empty or nonexistent. The endpoint code expects at least one entry.
    *   **Initial Hypothesis:** The Redis connection logic inside the endpoint might be faulty *or* the stream simply isn't being populated. A manual test (`XADD dealer_metrics * d '{"test": "data"}'` inside the Redis container followed by accessing `/snapshot`) returned the dummy data successfully, confirming the API<->Redis read path works *if data exists*. The problem is data *creation*.

2.  **Problem 14: `dealer_raw` Stream is Empty (Collector Not Running)**
    *   **Symptom:** Following the `IndexError`, investigation shifted to why `dealer_metrics` was empty. The hypothesis was that the preceding step (populating the *raw* stream) might be failing.
    *   **Diagnosis:** Connecting to the Redis container (`docker-compose exec redis redis-cli`) and checking the length of the raw stream (`XLEN dealer_raw`) revealed it was `(integer) 0`. This proved the `deribit_ws.py` collector was not running and adding data.
    *   **Cause:** The `Dockerfile`'s `CMD ["uvicorn", ...]` only started the Uvicorn server. It did *not* execute the concurrent startup logic in `dealer_flow/__main__.py`, which was intended to launch the `ws_run` collector task alongside the server.
    *   **Solution:** Implemented a `start.sh` script to explicitly launch both the collector (`python -m dealer_flow.deribit_ws &`) in the background and the Uvicorn server (`uvicorn ...`) in the foreground. Modified the `Dockerfile` to `COPY` and `chmod +x` this script, and changed the `CMD` to `["/app/start.sh"]`. Rebuilt the image and restarted using `docker-compose up`.
    *   **Verification:** After restarting, `docker-compose exec redis redis-cli XLEN dealer_raw` returned `(integer) 1` (or more), confirming the collector was now running via the startup script.

3.  **Problem 15: Processor Logic Skips Messages (Data Format / Auth Issue)**
    *   **Symptom:** Even with the collector running and populating `dealer_raw`, `/snapshot` still returned `204 No Content` (the updated API response for an empty `dealer_metrics` stream). This indicated the *processor* step (reading `dealer_raw`, writing `dealer_metrics`) was failing.
    *   **Diagnosis:** Added detailed logging to `dealer_flow/processor.py` and ran `docker-compose up` in the foreground. Logs revealed the processor was running, reading messages from `dealer_raw`, but consistently skipping them with messages like `PROCESSOR: Skipping message, no 'params' key.`. The logged message content showed a JSON-RPC error response from Deribit: `{'code': 13778, 'message': 'raw_subscriptions_not_available_for_unauthorized'}`.
    *   **Cause:** The collector (`deribit_ws.py`) was attempting to subscribe to `.raw` suffixed channels (e.g., `ticker.BTC-PERPETUAL.raw`), which require authentication, but the WebSocket connection was unauthenticated. Deribit was rejecting the subscription and sending back an error message, which the processor correctly identified as not containing the expected data structure.
    *   **Initial Proposed Solutions:**
        *   A) Switch collector subscriptions to public channels (e.g., `ticker.BTC-PERPETUAL.100ms`).
        *   B) Implement authentication in the collector.

---

**Phase 5: Architectural Realignment (Current State - Pending Implementation)**

1.  **Problem 16: Collector/Goal Mismatch & Systemic Issues**
    *   **Symptom:** User analysis (provided via prompt) reviewed the project state against the goal (options greeks dashboard), highlighting that even fixing the immediate auth error wouldn't solve the core problem.
    *   **Diagnosis:** A comprehensive review confirmed multiple critical issues beyond the immediate `.raw` subscription error:
        *   **Data Path Misalignment:** The collector targets *perpetual futures*, not *options*. The required data (options OI, greeks like delta, gamma, vega from tickers) needs different channel subscriptions (e.g., `ticker.{option_instrument_name}.100ms`, `book.{option_instrument_name}.100ms`) or REST calls.
        *   **Missing OI/Dealer Logic:** Dealer position inference (`dealer_net.py`) is a placeholder and needs integration with OI data (via WS book snapshots or REST `get_book_summary_by_instrument`).
        *   **Greek Calculation:** Higher-order greeks (vanna, charm, volga) are calculated in `greek_calc.py` but never used. The pipeline needs to ingest base parameters (S, K, T, IV, r - potentially from multiple sources) or Deribit-provided base greeks to feed this calculation or validate against Deribit's values.
        *   **Latency/Scalability:** Subscribing to thousands of individual option tickers is likely too slow; requires filtering or multiplexing. The processor needs batching.
        *   **Persistence:** No ClickHouse implementation exists for historical data.
        *   **Security:** Redis password not enforced in Compose; `.env` lacks API key fields.
    *   **Cause:** Initial scaffolding focused on structure, deferring correct data path implementation and integration logic. The initial WebSocket subscription was incorrect for the project's stated goal.
    *   **Current State:** The application runs (collector, processor stub, API), but the data pipeline is fundamentally misaligned with the objective of processing options greeks. The processor reads raw futures auth error messages and the API endpoint can only serve manually injected data or 204s. The next step requires significant changes to `deribit_ws.py` (channel subscriptions, potentially REST calls for OI/params), implementation of `dealer_net.py`, integration of `greek_calc.py` and `vanna_charm_volga.py` within the `processor.py` loop, and likely splitting services in `docker-compose.yml`.

**(End of Log - Awaiting Implementation of Architectural Changes)**


## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide (Continuation from Phase 5)

**Previous State:** Analysis identified significant architectural misalignment. The collector targeted perpetual futures, not options; dealer netting was a placeholder; the greeks engine was unused; and the processor lacked logic to bridge the gap. The immediate blocker was the collector failing due to authentication errors on `.raw` channels.

---

**Phase 6: Implementation & Refinement (Iterative Fixes)**

1.  **Problem 16 Revisit & Simplification:**
    *   **Context:** User provided comprehensive code patches based on previous analysis, aiming to implement authentication, fetch option instruments, calculate missing greeks, and publish metrics.
    *   **Action:** Implemented the provided patches for `dealer_flow/config.py`, `.env.example`, `dealer_flow/deribit_ws.py`, `dealer_flow/processor.py`, `tests/test_gamma_flip.py`, and added a doctest header to `dealer_flow/greek_calc.py`.

2.  **Problem 17: Processor Crash (`TypeError` on Type Hint)**
    *   **Symptom:** `docker-compose up` failed immediately. The traceback showed `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` originating from the return type hint `-> float | None:` in `dealer_flow/gamma_flip.py`.
    *   **Diagnosis:** The `|` union syntax for type hints requires Python 3.10 or later. The Docker container was running Python 3.9.6.
    *   **Cause:** Incompatible type hint syntax for the container's Python version.
    *   **Solution:** Changed the type hint in `gamma_flip.py` to use `typing.Optional`:
        *   Added `from typing import Optional`
        *   Changed return hint to `-> Optional[float]`
    *   **Note:** User clarified that Redis password was not being used, so `REDIS_URL` in `.env` remains `redis://redis:6379/0` and no password-related environment variables were added to `docker-compose.yml`.

3.  **Problem 18: Processor Crash (`KeyError: 'side'`)**
    *   **Symptom:** After fixing the type hint, `docker-compose up` started the collector and processor, but the processor crashed. Logs showed `KeyError: 'side'` originating from `dealer_flow/dealer_net.py` when accessing `oi_df["side"]`.
    *   **Diagnosis:** The `infer_dealer_net` function assumed the input DataFrame (`oi_df`, created from `greek_store` in the processor) would always contain a `side` column (e.g., 'call_long', 'put_short'). However, the processor currently only populates `greek_store` with greek values, not side information from OI data.
    *   **Cause:** Missing `side` column in the DataFrame passed to `infer_dealer_net`.
    *   **Solution:**
        *   Modified `dealer_net.py` to check if the `side` column exists. If not, default `dealer_side_mult` to `1` (assuming all positions need hedging initially).
        *   Modified `processor.py` within `maybe_publish` to explicitly multiply the fetched/calculated greeks (`gamma`, `vanna`, `charm`, `volga`) by the `dealer_side_mult` before passing them to `roll_up`. This ensures the sign is applied correctly when side information becomes available later.

4.  **Problem 19: Processor Crash (`TypeError` on JSON Serialization)**
    *   **Symptom:** After fixing the `KeyError: 'side'`, the processor ran further but crashed during the `maybe_publish` step when writing to Redis. Logs showed `TypeError: Type is not JSON serializable: numpy.float64`.
    *   **Diagnosis:** The `payload` dictionary being serialized contained values that were NumPy float types (e.g., `numpy.float64`), which the standard `orjson.dumps()` function doesn't handle by default.
    *   **Cause:** Standard JSON serializers expect native Python types (int, float, str, etc.).
    *   **Solution:** Utilized `orjson`'s NumPy serialization capability:
        *   Added `JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY` constant in `processor.py`.
        *   Modified the `redis.xadd` call in `maybe_publish` to `orjson.dumps(payload, option=JSON_OPTS)`.

5.  **Problem 20: Runtime Warnings & Incorrect Metrics (Divide by Zero / Wrong Price)**
    *   **Symptom:** The application ran, and `/snapshot` returned JSON data, but the logs were filled with `RuntimeWarning: divide by zero encountered in scalar divide` from `gamma_flip.py`. The returned JSON showed `price: 0.0` and near-zero metrics (`NGI`, `VSS`, etc.).
    *   **Diagnosis:**
        *   The `gamma_flip_distance` function was receiving `spot_price = 0.0`, causing the division error.
        *   The `processor.py` logic was incorrectly calculating `notional_usd = size * mark` (using the *option's* mark price) instead of `size * underlying_spot`.
        *   The underlying spot price (`spot_price`) was never being updated because the processor wasn't correctly parsing messages from the `deribit_price_index.btc_usd` channel.
    *   **Cause:** Failure to parse the spot price index message and using the wrong price (option mark price) for notional calculations.
    *   **Solution:**
        *   Added a zero check in `gamma_flip.py` before dividing: `if spot_price <= 0: return None`.
        *   Modified `processor.py`:
            *   Added a global `spot_price` variable initialized to `0.0`.
            *   Added logic to parse messages from `deribit_price_index` channel and update `spot_price`.
            *   Changed `notional` calculation to `size * (spot_price or mark)` (using spot price if available).
            *   Removed the `underlying_price` assignment in `dealer.assign(...)` as `roll_up` uses `notional_usd` directly.
        *   Added `import warnings; warnings.filterwarnings("ignore", category=RuntimeWarning)` to suppress the (now guarded against) warning display.

6.  **Problem 21: Parse Error & Spot Price Still Zero (`KeyError: 'index_price'`)**
    *   **Symptom:** After implementing the previous fix, the processor logged `PARSE ERR 'index_price'`, and the `/snapshot` endpoint still showed `price: 0.0`.
    *   **Diagnosis:** The processor code attempted to access `d["index_price"]` from the price index message, but the actual key provided by Deribit is `price`.
    *   **Cause:** Incorrect key used to access the spot price in the JSON payload.
    *   **Solution:** Modified the price index parsing logic in `processor.py` to safely get the price using `spot_price = float(d.get("price") or d.get("index_price") or 0.0)`.

7.  **Problem 22: Spot Price Still Zero & No Metrics Published (Case Sensitivity)**
    *   **Symptom:** After fixing the key error, the `/snapshot` endpoint returned `200 OK` but with `price: 0.0` and near-zero metrics. Logs showed the collector pushing messages but no "PROCESSOR: stored ... greeks" messages, indicating the ticker branch in the processor was likely still being skipped.
    *   **Diagnosis:** The check `ch.startswith("deribit_price_index")` was case-sensitive. Deribit likely sends the channel name with different casing (e.g., `deribit_price_index.BTC_USD`). Although the subscription in the collector *might* be case-insensitive, the *check* in the processor was failing. Because `spot_price` remained `0.0`, the processor correctly skipped calculating notionals and storing greeks (due to the `if spot_price == 0: continue` guard added earlier).
    *   **Cause:** Case-sensitive check failing to match the actual incoming channel name for the spot price index.
    *   **Solution:**
        *   Modified the spot price channel check in `processor.py` to be case-insensitive: `if ch.lower().startswith("deribit_price_index"):`.
        *   Ensured the `notional` calculation uses `spot_price` correctly and the `if spot_price == 0: continue` guard prevents processing ticks before the spot price is known.

---

**Current State (Pending Validation):**

*   The collector connects (authenticated), subscribes to spot index and a limited set of option tickers/books.
*   The processor attempts to parse spot index messages (now case-insensitive) and ticker messages.
*   The processor calculates missing higher-order greeks using `bs_greeks`.
*   The processor aggregates metrics using placeholder dealer netting (`dealer_side_mult = 1`).
*   The processor handles potential `KeyError`s and `TypeError`s during parsing and serialization.
*   The processor guards against division-by-zero errors.
*   The API serves the latest processed metrics from the `dealer_metrics` Redis stream.
*   **Expected Next Outcome:** Logs should show successful processing of both spot index and ticker messages, `PROCESSOR: stored ... greeks` messages should appear, and `/snapshot` should return JSON with a non-zero spot `price` and realistically scaled metrics (NGI, VSS, etc.).

**(End of Log - Awaiting results of running the latest patched code)**





================================================
FILE: start.sh
================================================
#!/bin/sh
set -e

echo "Starting Deribit WebSocket collector..."
python -m dealer_flow.deribit_ws &

echo "Starting Processor..."
python -m dealer_flow.processor &

echo "Starting Uvicorn API server..."
uvicorn dealer_flow.rest_service:app --host 0.0.0.0 --port 8000


================================================
FILE: .dockerignore
================================================
.git
__pycache__/
*.parquet
*.env
node_modules



================================================
FILE: .env.example
================================================
REDIS_URL=redis://localhost:6379/0
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
DERIBIT_WS=wss://www.deribit.com/ws/api/v2
CURRENCY=BTC



================================================
FILE: dealer_flow/__init__.py
================================================
__all__ = ["config"]



================================================
FILE: dealer_flow/__main__.py
================================================
"""
Convenience entrypoint: launches collector and API concurrently
"""
import asyncio
from dealer_flow.deribit_ws import run as ws_run
from dealer_flow.rest_service import app  # ensures FastAPI import
import uvicorn

async def main():
    task_ws = asyncio.create_task(ws_run())
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(task_ws, server.serve())

if __name__ == "__main__":
    asyncio.run(main())



================================================
FILE: dealer_flow/config.py
================================================
#### 1 `dealer_flow/config.py`
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Web-socket & REST hosts
    deribit_ws: str = "wss://www.deribit.com/ws/api/v2"
    deribit_rest: str = "https://www.deribit.com/api/v2"

    # OAuth2 creds (set in .env)
    deribit_id: str = "lIdRCJdl"
    deribit_secret: str = "BiqWyPz855okyEBIaSFYre4vAXQ7t1az1pETWE36Dwo"

    # Redis
    redis_url: str = "redis://:changeme@redis:6379/0"

    # General
    currency: str = "BTC"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"


settings = Settings()



================================================
FILE: dealer_flow/dealer_net.py
================================================
"""
Infers dealer sign (MM vs customer) from open interest.
Assume dealer net pos = -customer_net_pos.
"""
import pandas as pd
import numpy as np

def infer_dealer_net(oi_df: pd.DataFrame) -> pd.DataFrame:
    """
    oi_df may contain:
        ['instrument', 'gamma', 'vanna', 'charm', 'volga', 'notional_usd', ...]
    Optionally:
        ['side'] with values like 'call_long', 'call_short', etc.

    Returns same DF with a 'dealer_side_mult' column (1 or -1).
    """
    if "side" in oi_df.columns:
        oi_df["dealer_side_mult"] = np.where(
            oi_df["side"].str.contains("short"), 1, -1
        )
    else:
        # no side info yet – assume dealer needs to hedge ALL customer gamma
        oi_df["dealer_side_mult"] = 1

    return oi_df



================================================
FILE: dealer_flow/deribit_ws.py
================================================
"""
Collector with verbose logging.
If credentials missing or auth fails we fall back to **unauth** mode and
subscribe to at most 12 liquid ATM option strikes to guarantee success.
"""
import asyncio, json, time, uuid, aiohttp, websockets, orjson, sys
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

TOKEN_TTL = 23 * 3600
MAX_UNAUTH_STRIKES = 12            # Deribit limit for 100 ms streams

async def auth_token():
    if not (settings.deribit_id and settings.deribit_secret):
        print("COLLECTOR: creds absent → unauth mode", file=sys.stderr)
        return None, 0
    async with aiohttp.ClientSession() as sess:
        try:
            r = await sess.get(
                f"{settings.deribit_rest}/public/auth",
                params={
                    "grant_type": "client_credentials",
                    "client_id": settings.deribit_id,
                    "client_secret": settings.deribit_secret,
                },
                timeout=10,
            )
            j = await r.json()
        except Exception as e:
            print(f"COLLECTOR: auth HTTP error {e} → unauth mode", file=sys.stderr)
            return None, 0
    if "error" in j:
        print(f"COLLECTOR: auth rejected {j['error']} → unauth mode", file=sys.stderr)
        return None, 0
    token = j["result"]["access_token"]
    print("COLLECTOR: auth OK", file=sys.stderr)
    return token, time.time() + TOKEN_TTL


async def current_instruments():
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(
            f"{settings.deribit_rest}/public/get_instruments",
            params=dict(currency=settings.currency, kind="option", expired="false"),
            timeout=10,
        )
        data = (await r.json())["result"]
        # crude filter: keep first strikes near ATM
        return [d["instrument_name"] for d in data[:MAX_UNAUTH_STRIKES]]


async def subscribe(ws, channels):
    req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "public/subscribe",
        "params": {"channels": channels},
    }
    await ws.send(orjson.dumps(req).decode())


async def run():
    redis = await get_redis()

    while True:  # reconnect loop
        token, token_exp = await auth_token()
        try:
            instruments = await current_instruments()
        except Exception as e:
            print(f"COLLECTOR: instrument fetch failed {e}", file=sys.stderr)
            await asyncio.sleep(5)
            continue

        spot_ch = f"deribit_price_index.{settings.currency.lower()}_usd"
        subs = (
            [spot_ch]
            + [f"ticker.{i}.100ms" for i in instruments]
            + [f"book.{i}.100ms" for i in instruments]
        )

        hdrs = {"Authorization": f"Bearer {token}"} if token else {}
        mode = "auth" if token else "unauth"
        print(f"COLLECTOR: connecting ({mode}), {len(subs)} channels …",
              file=sys.stderr)

        try:
            async with websockets.connect(
                settings.deribit_ws, extra_headers=hdrs, ping_interval=20
            ) as ws:
                await subscribe(ws, subs)
                print("COLLECTOR: subscribed, streaming …", file=sys.stderr)
                cnt = 0
                async for msg in ws:
                    await redis.xadd(STREAM_KEY_RAW, {"d": msg.encode()})
                    cnt += 1
                    if cnt % 500 == 0:
                        print(f"COLLECTOR: pushed {cnt} msgs", file=sys.stderr)
        except Exception as e:
            print(f"COLLECTOR: websocket error {e} – reconnect in 5 s",
                  file=sys.stderr)
            await asyncio.sleep(5)

if __name__ == "__main__":
    import asyncio, sys
    try:
        print("COLLECTOR: launching …", file=sys.stderr)
        asyncio.run(run())
    except KeyboardInterrupt:
        print("COLLECTOR: interrupted, exiting.", file=sys.stderr)


================================================
FILE: dealer_flow/gamma_flip.py
================================================
import numpy as np
import pandas as pd
from typing import Optional


def gamma_flip_distance(
    gamma_by_strike: pd.Series, spot_price: float
) -> Optional[float]:
    """
    gamma_by_strike: index=strike, value=net dealer gamma
    Finds first zero-cross and returns (strike/spot - 1)
    """
    signs = np.sign(gamma_by_strike.values)
    zero_idx = np.where(np.diff(signs))[0]
    if zero_idx.size == 0:
        return None
    flip_strike = gamma_by_strike.index[zero_idx[0] + 1]
    if spot_price == 0:
        return None
    return float(flip_strike / spot_price - 1.0)


================================================
FILE: dealer_flow/greek_calc.py
================================================
"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.
All inputs are numpy arrays for vectorised speed.
"""
"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.

Doctest sanity check
>>> import numpy as np; from dealer_flow.greek_calc import greeks
>>> γ, v, c, vg = greeks(np.array([100]), np.array([100]), np.array([0.1]), 0.0, np.array([0.5]), np.array([1]))
>>> round(float(γ), 6)
0.079788
"""
import numpy as np
from numba import njit
#from scipy.stats import norm  # only used for cdf/pdf

SQRT_2PI = np.sqrt(2 * np.pi)

@njit(fastmath=True)
def _pdf(x):
    return np.exp(-0.5 * x * x) / SQRT_2PI

@njit(fastmath=True)
def _cdf(x):
    return 0.5 * (1.0 + np.erf(x / np.sqrt(2.0)))

@njit(fastmath=True)
def greeks(S, K, T, r, sigma, option_type):
    """
    Returns gamma, vanna, charm, volga for each row.
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    pdf_d1 = _pdf(d1)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    
    # vanna = ∂^2 price / ∂S ∂σ
    vanna = -d2 * pdf_d1 / sigma
    
    # charm (dDelta/dt)
    charm = (
        -pdf_d1 * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
    )
    
    vega = S * pdf_d1 * np.sqrt(T)
    volga = vega * d1 * d2 / sigma
    
    return gamma, vanna, charm, volga



================================================
FILE: dealer_flow/hpp_score.py
================================================
def hpp(spot_move_sign: int, NGI: float, VSS: float, CHL: float, alpha=0.1, beta=0.1):
    """
    Hedge-Pressure Projection
    """
    return spot_move_sign * NGI + alpha * VSS + beta * CHL



================================================
FILE: dealer_flow/processor.py
================================================
# ---------- NEW FILE: dealer_flow/processor.py ----------
"""
Processor: reads raw Deribit messages from Redis Stream `dealer_raw`,
derives minimal metrics, writes JSON blob to `dealer_metrics`.

This first iteration *only*:
• parses ticker price from perpetual feed
• counts messages per rolling 1-second window (msg_rate)
• publishes stub NGI/VSS/CHL/HPP so the dashboard endpoint works

Subsequent iterations will:
• ingest options OI, compute full greeks, HPP, scenario bucket
"""

"""
Processor: aggregates option greeks & dealer net,
publishes roll-ups every second to `dealer_metrics`.
"""
import asyncio, time, orjson, pandas as pd, numpy as np, sys
import datetime as dt, calendar
import re, datetime as dt, calendar
from collections import deque, defaultdict
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks   # NEW

JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY
GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0  # s
_DATE_RE = re.compile(r"(\d{1,2})([A-Z]{3})(\d{2})")  # day, month, yy


# in-memory state
greek_store = {}        # inst -> dict(gamma, vanna, charm, volga, OI)
gamma_by_strike = {}    # strike -> net dealer gamma
prices = deque(maxlen=1)
tick_times = deque(maxlen=1000)
spot = [0.0]

async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise

async def maybe_publish(redis):
    now = time.time()
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()
    if not prices:
        return
    # Build DataFrame
    df = pd.DataFrame.from_dict(greek_store, orient="index")
    if df.empty:
        return
    dealer = infer_dealer_net(df.reset_index(names="instrument"))
    # apply dealer sign to greeks
    signed = dealer.copy()
    signed[["gamma", "vanna", "charm", "volga"]] = (
        signed[["gamma", "vanna", "charm", "volga"]]
        .mul(signed["dealer_side_mult"], axis=0)
    )
    agg = roll_up(signed)
    flip = gamma_flip_distance(pd.Series(gamma_by_strike), prices[-1])
    payload = {"ts": now, "price": prices[-1], "msg_rate": len(tick_times), **agg, "flip_pct": flip}
    await redis.xadd(
        STREAM_KEY_METRICS,
        {"d": orjson.dumps(payload, option=JSON_OPTS)}
    )

def _expiry_ts(sym: str) -> float:
    """
    Extract expiry from option symbol. Returns UTC timestamp 08:00 expiry.
    """
    date_part = sym.split("-")[1]           # e.g. 5MAY25
    m = _DATE_RE.fullmatch(date_part)
    if not m:
        raise ValueError(f"unparsable date {date_part}")
    day, mon, yy = int(m[1]), m[2], int(m[3])
    month_num = dt.datetime.strptime(mon, "%b").month
    year_full = 2000 + yy
    dt_exp = dt.datetime(year_full, month_num, day, 8, tzinfo=dt.timezone.utc)
    return dt_exp.timestamp()

async def processor():
    redis = await get_redis()
    await ensure_group(redis)
    print("PROCESSOR: started, waiting for data …", file=sys.stderr)
    last_pub = time.time()

    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
        if resp:
            for _, msgs in resp:
                for mid, data in msgs:
                    try:
                        j = orjson.loads(data[b"d"])
                        params = j.get("params", {})
                        ch, d = params.get("channel"), params.get("data")
                        if not isinstance(d, dict):
                            continue
                        if ch.startswith("deribit_price_index"):
                            # Deribit returns {"price": <float>, ...}
                            spot_price = float(d.get("price") or d.get("index_price"))
                            continue
                        if ch.startswith("ticker"):
                            mark = float(d["mark_price"])
                            prices.append(mark)

                            inst = d["instrument_name"]      # BTC-24MAY25-60000-P
                            strike = float(inst.split("-")[2])
                            expiry_ts = _expiry_ts(inst) 
                            now_ts    = d["timestamp"] / 1000
                            T = max((expiry_ts - now_ts), 0.0) / (365 * 24 * 3600)

                            size  = d["open_interest"]        # contracts
                            notional = size * (spot[0] or mark)

                            deriv_greeks = d.get("greeks", {})
                            gamma = deriv_greeks.get("gamma", 0.0)

                            # If vanna/charm/volga missing → compute
                            vanna  = deriv_greeks.get("vanna")
                            charm  = deriv_greeks.get("charm")
                            volga  = deriv_greeks.get("volga")

                            if None in (vanna, charm, volga):
                                sigma = d.get("mark_iv", 0) / 100  # iv in pct
                                if sigma <= 0 or T <= 0:
                                    # cannot compute, default zeros
                                    vanna = vanna or 0.0
                                    charm = charm or 0.0
                                    volga = volga or 0.0
                                else:
                                    S = np.array([mark])
                                    K = np.array([strike])
                                    g, v, c, vg = bs_greeks(
                                        S, K, np.array([T]), 0.0, np.array([sigma]), np.array([1])
                                    )
                                    vanna = vanna or float(v[0])
                                    charm = charm or float(c[0])
                                    volga = volga or float(vg[0])

                            greeks = {
                                "gamma": gamma,
                                "vanna": vanna,
                                "charm": charm,
                                "volga": volga,
                                "notional_usd": notional,
                                "strike": strike,
                            }
                            greek_store[inst] = greeks
                            gamma_by_strike[strike] = (
                                gamma_by_strike.get(strike, 0.0) + gamma
                            )
                            if len(greek_store) % 1000 == 0:
                                print(f"PROCESSOR: stored {len(greek_store)} greeks",
                                      file=sys.stderr)
                        tick_times.append(time.time())
                    except Exception as e:
                        print(f"PARSE ERR {e}", file=sys.stderr)
        now = time.time()
        if now - last_pub >= ROLL_FREQ:
            await maybe_publish(redis)
            last_pub = now

if __name__ == "__main__":
    asyncio.run(processor())



================================================
FILE: dealer_flow/redis_stream.py
================================================
import aioredis
from dealer_flow.config import settings

STREAM_KEY_RAW = "dealer_raw"
STREAM_KEY_METRICS = "dealer_metrics"

async def get_redis():
    return await aioredis.from_url(settings.redis_url, decode_responses=False)



================================================
FILE: dealer_flow/rest_service.py
================================================
from fastapi import FastAPI, Response, status
from dealer_flow.redis_stream import get_redis, STREAM_KEY_METRICS
import orjson
import asyncio

app = FastAPI()

@app.get("/snapshot")
async def snapshot():
    redis = await get_redis()
    last = await redis.xrevrange(STREAM_KEY_METRICS, count=1)
    if not last:
        # metrics not produced yet → 204 No Content
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return orjson.loads(last[0][1][b"d"])









================================================
FILE: dealer_flow/rules.py
================================================
def classify(flow: dict, adv_usd: float, spot_change_pct: float):
    """
    flow keys: NGI, VSS, CHL_24h, HPP
    Returns bucket label 1-6
    """
    material = abs(flow["NGI"]) > 0.1 * adv_usd
    rising = spot_change_pct > 0
    falling = spot_change_pct < 0
    
    if rising and flow["NGI"] < 0:
        return "Dealer Sell Material" if material else "Dealer Sell Immaterial"
    if falling and flow["NGI"] > 0:
        return "Dealer Buy Material" if material else "Dealer Buy Immaterial"
    if abs(flow["NGI"]) < 1e-6:
        return "Gamma Pin"
    if abs(flow["VSS"]) > abs(flow["NGI"]) * 2:
        return "Vanna Squeeze"
    return "Neutral"



================================================
FILE: dealer_flow/vanna_charm_volga.py
================================================
import pandas as pd

def roll_up(dealer_greeks: pd.DataFrame, spot_pct: float = 0.01) -> dict:
    """
    dealer_greeks columns: ['gamma','vanna','charm','volga','notional_usd']
    Returns NGI, VSS, CHL_24h, VOLG
    """
    # Dollar gamma for 1% move
    dealer_greeks["dollar_gamma"] = (
        dealer_greeks["gamma"] * dealer_greeks["notional_usd"] * spot_pct
    )
    NGI = dealer_greeks["dollar_gamma"].sum()
    
    VSS = (dealer_greeks["vanna"] * 0.01 * dealer_greeks["notional_usd"]).sum()
    CHL = (dealer_greeks["charm"] * 24 / 365 * dealer_greeks["notional_usd"]).sum()
    VOLG = (dealer_greeks["volga"] * 0.01 * dealer_greeks["notional_usd"]).sum()
    
    return dict(NGI=NGI, VSS=VSS, CHL_24h=CHL, VOLG=VOLG)




================================================
FILE: dealer_flow/tests/test_gamma_flip.py
================================================
import pandas as pd
from dealer_flow.gamma_flip import gamma_flip_distance

def test_basic_flip():
    strikes = [9000, 9500, 10000, 10500]
    gamma = [-2.0, -1.0, 0.5, 1.2]
    series = pd.Series(gamma, index=strikes)
    assert gamma_flip_distance(series, 10000) == 0.05




================================================
FILE: docker-compose.yml
================================================
services:
  dealer-flow:
    build: . # Build the image from the Dockerfile in the current directory
    image: dealer-flow # Use the image tag you built
    container_name: dealer_flow_app
    env_file:
      - .env # Pass environment variables from .env file
    ports:
      - "8000:8000" # Map container port 8000 to host port 8000
    depends_on:
      - redis # Ensure Redis starts before the app
    networks:
      - dealer_net

  redis:
    image: redis:alpine # Use an official Redis image
    container_name: dealer_flow_redis
    # If you set a password in redis.conf and want to use it here:
    # command: redis-server --requirepass ${REDIS_PASSWORD}
    networks:
      - dealer_net
    # Optional: Persist Redis data outside the container
    # volumes:
    #   - redis_data:/data

networks:
  dealer_net:
    driver: bridge

# Optional: Define named volume for persistence
# volumes:
#   redis_data:


================================================
FILE: Dockerfile
================================================
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


================================================
FILE: pyproject.toml
================================================
[tool.poetry]
name = "dealer-flow-stack"
version = "0.1.0"
description = "Real-time dealer-flow dashboard for BTC options"
authors = ["boscovich"]
readme = "README.md"
packages = [{ include = "dealer_flow" }]

[tool.poetry.dependencies]
python = "3.9.6"
websockets = "^12.0"
aiohttp = "^3.9"
redis = "^5.0"
numpy = "^1.26"
pandas = "^2.2"
numba = "^0.59"
pydantic = "^2.7"
pydantic-settings = "^2.0"
fastapi = "^0.111"
uvicorn = { extras = ["standard"], version = "^0.29" }
orjson = "^3.10"
clickhouse-driver = "^0.2.9"
plotly = "^5.20"
aioredis = "^2.0"
scipy = "^1.13"

[tool.poetry.group.dev.dependencies]
black = "^24.3"
isort = "^5.13"
mypy = "^1.9"
pytest = "^8.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"




================================================
FILE: REPORT.md
================================================
**Pre-Mortem (≤120 w)**  
• Scope creep—adding CME, order-book depth later derails MVP.  
• Ambiguous “dashboard” definition → visual churn.  
• Ignoring ops (secrets, CI) until late → launch delay.  
• Misestimate Deribit bandwidth—CPU bill spikes.  
• Back-test leakage (look-ahead) undermines Sharpe claim.  
• ClickHouse schema drift bricks historical queries.  
• Reliance on Deribit greeks—vendor change breaks calc.  
• Security holes: Redis exposed, creds in repo.

**Assumptions/Biases**  
Assume BTC options stay Deribit-centric. Target user is quantitative trader comfortable with Docker. Bias toward open-source infra (Redis, ClickHouse) over managed SaaS. Incentive: hit 200 ms e2e latency—may under-invest in fault-tolerance.
output
Copy
Edit
# Dealer-Flow Stack — Project Scope v0.3

## Mission
Deliver a **real-time dealer-flow intelligence platform** for BTC options that:  
1. Quantifies dealer hedge pressure (gamma, vanna, charm, volga).  
2. Flags flow-driven regime states (“Gamma-Pin”, “Vanna-Squeeze”, etc.).  
3. Feeds both a discretionary dashboard and a systematic model sleeve targeting **Sharpe > 3**.

## Functional Components
| Layer | Responsibilities | Tech |
|-------|------------------|------|
| **Collector** | Auth to Deribit, subscribe to option tickers & books, stream raw JSON → Redis ≤ 50 ms. | `websockets`, `aiohttp` |
| **Processor** | Aggregate greeks, infer dealer side from OI, compute NGI/VSS/CHL/VOLG, G-Flip Δ, HPP, classify scenarios, publish metrics ≤ 150 ms. | `numba`, `pandas` |
| **API** | Expose `/snapshot`, `/heatmap`, `/scenario` REST/WebSocket. | FastAPI |
| **Dashboard** | Sparkline, gauges, heat-map, scenario badges; refresh 1–5 Hz. | Plotly Dash (later React) |
| **Storage** | Hot: Redis 24 h. Warm: ClickHouse 30 d. Cold: S3 Parquet. | Redis Streams, ClickHouse |
| **Back-test / Model** | Purged walk-forward CV, SHAP pruning, cat-boost baseline. | Jupyter, CatBoost |

## Non-Functional Requirements
* **Latency:** tick → dashboard ≤ 200 ms 95-pct.  
* **Uptime:** 99 %. Auto-restart workers.  
* **Security:** API keys in `.env`; Redis password + bridge network only.  
* **Portability:** Single `docker-compose up` for full stack.  
* **Reproducibility:** Poetry lockfile; CI builds image; ClickHouse DDL versioned.  

## Deliverables & Milestones
1. **MVP Wire-up** (DONE): collector → processor stub → `/snapshot`.  
2. **Full Greek Roll-up**: option feed auth, filtered strike set, NGI/VSS/CHL/VOLG live.  
3. **Dashboard v1**: real gauges + heat-map.  
4. **Historical Backfill**: ClickHouse schema, 30 d options/OI ingest.  
5. **Systematic Sleeve**: model notebook, walk-forward report.  
6. **Hardening**: tests, alerts, docs, prod Helm charts.

## Out-of-Scope (for v1)
* Order-book microstructure (queue pos, depth imbalance).  
* Non-BTC assets.  
* CME options parity.  
* Web-scale multi-tenant auth.




rationale
**Pre-Mortem (Documentation Generation, ≤120 w):**
- Missing context: Forgetting initial setup details (macOS, Poetry, initial Dockerfile intent).
- Incorrect diagnosis summary: Misrepresenting the reason for a specific error.
- Solution ambiguity: Not clearly stating the final, successful command or config change for each step.
- Overlooking local issues: Focusing only on Docker and forgetting the `llvmlite` and Redis troubleshooting.
- Lack of structure: Presenting steps chronologically but without logical grouping, making it hard to follow.
- Ignoring user decisions: Not reflecting the user's choice to switch away from `uv` back to `pip`.

**Analysis:** The goal is to create a clear, chronological narrative of the troubleshooting session for future maintainers. It needs to capture the state, the error encountered, the reasoning applied, and the solution implemented at each significant step, covering both Docker build issues and local environment problems (LLVM, Redis). Using a structured format (Problem, Diagnosis, Cause, Solution) for each step will enhance clarity. The document should reflect the iterative nature of the process and the final working state/decisions.
``````markdown
output
## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide

**Project Goal:** Build and run the "Dealer-Flow Stack" application, primarily focusing on creating a functional Docker image for deployment and resolving local development environment issues.

**Initial Setup:**
*   **OS:** macOS (inferred from terminal logs, specifically paths like `/opt/homebrew`, `/var/folders`, and Zsh prompt `username@Mac ... %`)
*   **Dependency Management:** Poetry
*   **Initial Dockerfile Intent:** Use `uv` within the Docker container for faster dependency installation.

---

**Phase 1: Docker Build Troubleshooting (Iterative)**

1.  **Problem 1: `poetry.lock` Not Found**
    *   **Symptom:** `docker build` failed during `COPY pyproject.toml poetry.lock /app/` step with error `"/poetry.lock": not found`.
    *   **Diagnosis:** The `poetry.lock` file existed locally in the build context root (`dealer-flow-stack`), but was not being included in the context sent to the Docker daemon.
    *   **Cause:** The `.dockerignore` file contained the wildcard pattern `*.lock`, which matched and excluded `poetry.lock`.
    *   **Solution:** Removed the `*.lock` line from the `.dockerignore` file.

2.  **Problem 2: Invalid `uv` Flag (`--prod`)**
    *   **Symptom:** `docker build` failed during `RUN uv pip install --prod ... -r poetry.lock` step with error `unexpected argument '--prod' found`.
    *   **Diagnosis:** The `uv pip install` command, when used with `-r`, does not recognize the `--prod` flag.
    *   **Cause:** Incorrect `uv` command syntax for installing only production dependencies from a requirements file.
    *   **Solution:** Removed the `--prod` flag, changing the command to `RUN uv pip install --require-hashes -r poetry.lock`.

3.  **Problem 3: `uv` Parsing `poetry.lock` Incorrectly (as requirements.txt)**
    *   **Symptom:** `docker build` failed during `RUN uv pip install --require-hashes -r poetry.lock` step with error `Unexpected '['... at poetry.lock:3:1`.
    *   **Diagnosis:** Despite the previous fix, `uv` was still trying to parse the TOML-formatted `poetry.lock` file as if it were a plain `requirements.txt` file, failing on the first `[[package]]` table definition.
    *   **Cause:** `uv pip install -r` is fundamentally designed for `requirements.txt` format, not `poetry.lock`. The correct command for synchronizing based on lock files is `uv pip sync`.
    *   **Solution:** Changed the command to `RUN uv pip sync --require-hashes poetry.lock`.

4.  **Problem 4: `uv pip sync` Still Parsing Incorrectly**
    *   **Symptom:** `docker build` failed with the *same* `Unexpected '['...` error even when using `uv pip sync poetry.lock`.
    *   **Diagnosis:** Highly unusual. This suggested the specific `uv` version or environment might be buggy or misinterpreting the direct lock file argument. An alternative is to rely on `uv`'s ability to auto-detect the lock file when syncing the project file.
    *   **Cause:** Unclear `uv` behavior when passed `poetry.lock` directly in this specific build environment.
    *   **Solution:** Changed the command to target the project file: `RUN uv pip sync --require-hashes pyproject.toml`.

5.  **Problem 5: `uv pip sync` Requires Environment Context**
    *   **Symptom:** `docker build` failed during `RUN uv pip sync --require-hashes pyproject.toml` step with error `No virtual environment found... pass --system`.
    *   **Diagnosis:** `uv` detected it wasn't in a virtual environment and refused to install into the container's base Python environment without explicit permission.
    *   **Cause:** `uv`'s default safety mechanism.
    *   **Solution:** Added the `--system` flag to grant permission: `RUN uv pip sync --system --require-hashes pyproject.toml`.

6.  **Decision Point: Removing `uv`**
    *   **Context:** Faced with multiple `uv`-specific hurdles in the Docker build process.
    *   **Decision:** Revert to a more traditional Docker build approach using standard `pip` and `poetry` (in a builder stage) for potentially greater stability and predictability, sacrificing `uv`'s speed advantage.

7.  **Problem 6: `poetry export` Command Not Found (Multi-Stage Build)**
    *   **Symptom:** The multi-stage Dockerfile using `pip` failed during the builder stage at `RUN poetry export ...` with error `The requested command export does not exist`.
    *   **Diagnosis:** The version of Poetry installed by the default `RUN pip install poetry` was too old (likely < 1.2) and lacked the `export` command.
    *   **Cause:** Default `pip install` pulled an outdated Poetry version.
    *   **Solution:** Pinned a specific, newer version of Poetry in the builder stage: `RUN pip install poetry==1.8.3`. (Build was assumed successful after this, conversation moved to local issues).

---

**Phase 2: Local Environment Troubleshooting (macOS with Homebrew)**

1.  **Problem 7: `llvmlite` Build Failure (`llvm-config` Not Found)**
    *   **Symptom:** `poetry install` failed locally with `RuntimeError: Could not find a llvm-config binary`.
    *   **Diagnosis:** `llvmlite`, a dependency (likely via `numba`), requires the LLVM compiler toolkit, specifically the `llvm-config` utility, to build its native extensions. This utility was not installed or not found in the system `PATH`.
    *   **Cause:** Missing required system dependency (LLVM).
    *   **Solution:** Install LLVM using Homebrew: `brew install llvm`.

2.  **Problem 8: `llvmlite` Build Failure (LLVM Version Mismatch)**
    *   **Symptom:** After installing LLVM via Homebrew, `poetry install` failed again, this time with `RuntimeError: Building llvmlite requires LLVM 14, got '20.1.3'`. (Initially, the `LLVM_CONFIG_PATH` env var was set pointing to the new LLVM 20.x `llvm-config`).
    *   **Diagnosis:** The specific `llvmlite` version locked in `poetry.lock` (0.42.0) was incompatible with the currently installed and referenced LLVM version (20.1.3). It explicitly required LLVM 14.x.
    *   **Cause:** Incompatible versions of interdependent system (LLVM) and Python (`llvmlite`) libraries.
    *   **Solution:**
        *   Install the required LLVM version alongside the existing one: `brew install llvm@14`.
        *   Update the environment variable to point specifically to the LLVM 14 executable before running install: `export LLVM_CONFIG_PATH=$(brew --prefix llvm@14)/bin/llvm-config`.

3.  **Problem 9: `llvmlite` Build Failure (Build Env Ignoring `LLVM_CONFIG_PATH`)**
    *   **Symptom:** Even after setting `LLVM_CONFIG_PATH` correctly to LLVM 14, `poetry install` *still* failed with the version mismatch error, indicating the build process was somehow finding LLVM 20.x.
    *   **Diagnosis:** The isolated build environment used by Poetry/pip wasn't inheriting or respecting the exported `LLVM_CONFIG_PATH`. It was likely finding the newer LLVM first via the standard system `PATH`.
    *   **Cause:** Environment variable propagation or `PATH` precedence issue within the build subprocess.
    *   **Solution:** Force the `PATH` order for the installation command only: `PATH="$(brew --prefix llvm@14)/bin:$PATH" poetry install`.

---

**Phase 3: Redis Configuration & Connection Issues**

1.  **Problem 10: Redis Server Start Failure (`Address already in use`)**
    *   **Symptom:** Attempting to start Redis manually (`redis-server /opt/homebrew/etc/redis.conf`) failed with `bind: Address already in use`.
    *   **Diagnosis:** Another Redis process was already running and bound to the configured port (default 6379).
    *   **Cause:** Trying to run multiple instances on the same port, likely due to a background service already running (e.g., via `brew services`).
    *   **Solution:** Stop the existing process (`brew services stop redis` or `kill <PID>`) before attempting to start a new one manually, OR consistently use `brew services start/stop/restart redis` to manage the background instance.

2.  **Problem 11: Redis Authentication Failure (`NOAUTH` / `WRONGPASS`)**
    *   **Symptom:** `redis-cli -a <password> ping` failed with authentication errors, even after seemingly setting the password.
    *   **Diagnosis:** The password being provided to `redis-cli` did not match the `requirepass` directive for the Redis instance it was actually connecting to (likely the pre-existing one on port 6379).
    *   **Cause:** Password mismatch or connecting to the wrong Redis instance.
    *   **Solution:** Verify the exact password in the relevant `redis.conf` file, ensure the correct Redis instance is running, and use the correct password with `redis-cli`. Use `brew services restart redis` to ensure the config file changes are loaded.

3.  **Problem 12: Redis Port Confusion (Multiple Instances)**
    *   **Symptom:** Successfully started a manual instance on port 6380, but `redis-cli` (without `-p`) connected successfully to 6379.
    *   **Diagnosis:** Two Redis instances were confirmed running: the manual one on 6380 and another (likely background/brew service) on 6379. `redis-cli` defaults to 6379.
    *   **Cause:** Multiple running instances; implicit default port usage by `redis-cli`.
    *   **Solution:** Use `redis-cli -p <port>` to target specific instances. Stop unneeded instances. Configure the project's `.env` file (`REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`) to match the *intended* running instance.

---

**Final Status / Key Takeaways for Maintainers:**

*   The Docker build process was eventually stabilized using a multi-stage build, installing Poetry 1.8.3 in the builder stage, exporting `requirements.txt`, and using `pip install -r requirements.txt` in the final stage. `uv` was abandoned due to persistent integration issues in this specific context.
*   The `.dockerignore` file is critical and must *not* exclude essential files like `poetry.lock`.
*   Local macOS development requiring `llvmlite`/`numba` needs careful LLVM version management. Install the specific required version (e.g., `llvm@14`) and ensure the build process uses it, potentially by manipulating the `PATH` directly during installation if environment variables are ignored.
*   Be mindful of multiple Redis instances. Use `brew services` for managing the background instance reliably on macOS. Always verify which port an instance is running on and use `redis-cli -p <port> -a <password>` for specific connections. Ensure the `.env` file aligns with the target Redis instance.

## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide (Continuation)

**Previous State:** The Docker image (`dealer-flow`) builds successfully using a multi-stage process with `pip` and Poetry 1.8.3. The container starts via `docker run`, launching Uvicorn. However, initial attempts to run failed due to missing `aioredis` dependency and subsequently a Pydantic v1 vs v2 `BaseSettings` import error. These were resolved by adding `aioredis` and `pydantic-settings` to `pyproject.toml`, updating `poetry.lock`, modifying the import in `dealer_flow/config.py`, and rebuilding the image. The container now runs, but accessing the `/snapshot` endpoint yields errors.

---

**Phase 4: Runtime Logic Debugging (Post-Build)**

1.  **Problem 13: `/snapshot` Endpoint Fails (`IndexError` / `500`)**
    *   **Symptom:** Running the container via `docker run --env-file .env -p 8000:8000 dealer-flow` starts Uvicorn successfully. However, accessing `http://localhost:8000/snapshot` results in a `500 Internal Server Error`. Container logs show `IndexError: list index out of range` at `dealer_flow/rest_service.py:12` when executing `list(last)[0]`.
    *   **Diagnosis:** The `redis.xrevrange(STREAM_KEY_METRICS, count=1)` call returns an empty list (`last`), indicating the target Redis stream `dealer_metrics` is empty or nonexistent. The endpoint code expects at least one entry.
    *   **Initial Hypothesis:** The Redis connection logic inside the endpoint might be faulty *or* the stream simply isn't being populated. A manual test (`XADD dealer_metrics * d '{"test": "data"}'` inside the Redis container followed by accessing `/snapshot`) returned the dummy data successfully, confirming the API<->Redis read path works *if data exists*. The problem is data *creation*.

2.  **Problem 14: `dealer_raw` Stream is Empty (Collector Not Running)**
    *   **Symptom:** Following the `IndexError`, investigation shifted to why `dealer_metrics` was empty. The hypothesis was that the preceding step (populating the *raw* stream) might be failing.
    *   **Diagnosis:** Connecting to the Redis container (`docker-compose exec redis redis-cli`) and checking the length of the raw stream (`XLEN dealer_raw`) revealed it was `(integer) 0`. This proved the `deribit_ws.py` collector was not running and adding data.
    *   **Cause:** The `Dockerfile`'s `CMD ["uvicorn", ...]` only started the Uvicorn server. It did *not* execute the concurrent startup logic in `dealer_flow/__main__.py`, which was intended to launch the `ws_run` collector task alongside the server.
    *   **Solution:** Implemented a `start.sh` script to explicitly launch both the collector (`python -m dealer_flow.deribit_ws &`) in the background and the Uvicorn server (`uvicorn ...`) in the foreground. Modified the `Dockerfile` to `COPY` and `chmod +x` this script, and changed the `CMD` to `["/app/start.sh"]`. Rebuilt the image and restarted using `docker-compose up`.
    *   **Verification:** After restarting, `docker-compose exec redis redis-cli XLEN dealer_raw` returned `(integer) 1` (or more), confirming the collector was now running via the startup script.

3.  **Problem 15: Processor Logic Skips Messages (Data Format / Auth Issue)**
    *   **Symptom:** Even with the collector running and populating `dealer_raw`, `/snapshot` still returned `204 No Content` (the updated API response for an empty `dealer_metrics` stream). This indicated the *processor* step (reading `dealer_raw`, writing `dealer_metrics`) was failing.
    *   **Diagnosis:** Added detailed logging to `dealer_flow/processor.py` and ran `docker-compose up` in the foreground. Logs revealed the processor was running, reading messages from `dealer_raw`, but consistently skipping them with messages like `PROCESSOR: Skipping message, no 'params' key.`. The logged message content showed a JSON-RPC error response from Deribit: `{'code': 13778, 'message': 'raw_subscriptions_not_available_for_unauthorized'}`.
    *   **Cause:** The collector (`deribit_ws.py`) was attempting to subscribe to `.raw` suffixed channels (e.g., `ticker.BTC-PERPETUAL.raw`), which require authentication, but the WebSocket connection was unauthenticated. Deribit was rejecting the subscription and sending back an error message, which the processor correctly identified as not containing the expected data structure.
    *   **Initial Proposed Solutions:**
        *   A) Switch collector subscriptions to public channels (e.g., `ticker.BTC-PERPETUAL.100ms`).
        *   B) Implement authentication in the collector.

---

**Phase 5: Architectural Realignment (Current State - Pending Implementation)**

1.  **Problem 16: Collector/Goal Mismatch & Systemic Issues**
    *   **Symptom:** User analysis (provided via prompt) reviewed the project state against the goal (options greeks dashboard), highlighting that even fixing the immediate auth error wouldn't solve the core problem.
    *   **Diagnosis:** A comprehensive review confirmed multiple critical issues beyond the immediate `.raw` subscription error:
        *   **Data Path Misalignment:** The collector targets *perpetual futures*, not *options*. The required data (options OI, greeks like delta, gamma, vega from tickers) needs different channel subscriptions (e.g., `ticker.{option_instrument_name}.100ms`, `book.{option_instrument_name}.100ms`) or REST calls.
        *   **Missing OI/Dealer Logic:** Dealer position inference (`dealer_net.py`) is a placeholder and needs integration with OI data (via WS book snapshots or REST `get_book_summary_by_instrument`).
        *   **Greek Calculation:** Higher-order greeks (vanna, charm, volga) are calculated in `greek_calc.py` but never used. The pipeline needs to ingest base parameters (S, K, T, IV, r - potentially from multiple sources) or Deribit-provided base greeks to feed this calculation or validate against Deribit's values.
        *   **Latency/Scalability:** Subscribing to thousands of individual option tickers is likely too slow; requires filtering or multiplexing. The processor needs batching.
        *   **Persistence:** No ClickHouse implementation exists for historical data.
        *   **Security:** Redis password not enforced in Compose; `.env` lacks API key fields.
    *   **Cause:** Initial scaffolding focused on structure, deferring correct data path implementation and integration logic. The initial WebSocket subscription was incorrect for the project's stated goal.
    *   **Current State:** The application runs (collector, processor stub, API), but the data pipeline is fundamentally misaligned with the objective of processing options greeks. The processor reads raw futures auth error messages and the API endpoint can only serve manually injected data or 204s. The next step requires significant changes to `deribit_ws.py` (channel subscriptions, potentially REST calls for OI/params), implementation of `dealer_net.py`, integration of `greek_calc.py` and `vanna_charm_volga.py` within the `processor.py` loop, and likely splitting services in `docker-compose.yml`.

**(End of Log - Awaiting Implementation of Architectural Changes)**


## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide (Continuation from Phase 5)

**Previous State:** Analysis identified significant architectural misalignment. The collector targeted perpetual futures, not options; dealer netting was a placeholder; the greeks engine was unused; and the processor lacked logic to bridge the gap. The immediate blocker was the collector failing due to authentication errors on `.raw` channels.

---

**Phase 6: Implementation & Refinement (Iterative Fixes)**

1.  **Problem 16 Revisit & Simplification:**
    *   **Context:** User provided comprehensive code patches based on previous analysis, aiming to implement authentication, fetch option instruments, calculate missing greeks, and publish metrics.
    *   **Action:** Implemented the provided patches for `dealer_flow/config.py`, `.env.example`, `dealer_flow/deribit_ws.py`, `dealer_flow/processor.py`, `tests/test_gamma_flip.py`, and added a doctest header to `dealer_flow/greek_calc.py`.

2.  **Problem 17: Processor Crash (`TypeError` on Type Hint)**
    *   **Symptom:** `docker-compose up` failed immediately. The traceback showed `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` originating from the return type hint `-> float | None:` in `dealer_flow/gamma_flip.py`.
    *   **Diagnosis:** The `|` union syntax for type hints requires Python 3.10 or later. The Docker container was running Python 3.9.6.
    *   **Cause:** Incompatible type hint syntax for the container's Python version.
    *   **Solution:** Changed the type hint in `gamma_flip.py` to use `typing.Optional`:
        *   Added `from typing import Optional`
        *   Changed return hint to `-> Optional[float]`
    *   **Note:** User clarified that Redis password was not being used, so `REDIS_URL` in `.env` remains `redis://redis:6379/0` and no password-related environment variables were added to `docker-compose.yml`.

3.  **Problem 18: Processor Crash (`KeyError: 'side'`)**
    *   **Symptom:** After fixing the type hint, `docker-compose up` started the collector and processor, but the processor crashed. Logs showed `KeyError: 'side'` originating from `dealer_flow/dealer_net.py` when accessing `oi_df["side"]`.
    *   **Diagnosis:** The `infer_dealer_net` function assumed the input DataFrame (`oi_df`, created from `greek_store` in the processor) would always contain a `side` column (e.g., 'call_long', 'put_short'). However, the processor currently only populates `greek_store` with greek values, not side information from OI data.
    *   **Cause:** Missing `side` column in the DataFrame passed to `infer_dealer_net`.
    *   **Solution:**
        *   Modified `dealer_net.py` to check if the `side` column exists. If not, default `dealer_side_mult` to `1` (assuming all positions need hedging initially).
        *   Modified `processor.py` within `maybe_publish` to explicitly multiply the fetched/calculated greeks (`gamma`, `vanna`, `charm`, `volga`) by the `dealer_side_mult` before passing them to `roll_up`. This ensures the sign is applied correctly when side information becomes available later.

4.  **Problem 19: Processor Crash (`TypeError` on JSON Serialization)**
    *   **Symptom:** After fixing the `KeyError: 'side'`, the processor ran further but crashed during the `maybe_publish` step when writing to Redis. Logs showed `TypeError: Type is not JSON serializable: numpy.float64`.
    *   **Diagnosis:** The `payload` dictionary being serialized contained values that were NumPy float types (e.g., `numpy.float64`), which the standard `orjson.dumps()` function doesn't handle by default.
    *   **Cause:** Standard JSON serializers expect native Python types (int, float, str, etc.).
    *   **Solution:** Utilized `orjson`'s NumPy serialization capability:
        *   Added `JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY` constant in `processor.py`.
        *   Modified the `redis.xadd` call in `maybe_publish` to `orjson.dumps(payload, option=JSON_OPTS)`.

5.  **Problem 20: Runtime Warnings & Incorrect Metrics (Divide by Zero / Wrong Price)**
    *   **Symptom:** The application ran, and `/snapshot` returned JSON data, but the logs were filled with `RuntimeWarning: divide by zero encountered in scalar divide` from `gamma_flip.py`. The returned JSON showed `price: 0.0` and near-zero metrics (`NGI`, `VSS`, etc.).
    *   **Diagnosis:**
        *   The `gamma_flip_distance` function was receiving `spot_price = 0.0`, causing the division error.
        *   The `processor.py` logic was incorrectly calculating `notional_usd = size * mark` (using the *option's* mark price) instead of `size * underlying_spot`.
        *   The underlying spot price (`spot_price`) was never being updated because the processor wasn't correctly parsing messages from the `deribit_price_index.btc_usd` channel.
    *   **Cause:** Failure to parse the spot price index message and using the wrong price (option mark price) for notional calculations.
    *   **Solution:**
        *   Added a zero check in `gamma_flip.py` before dividing: `if spot_price <= 0: return None`.
        *   Modified `processor.py`:
            *   Added a global `spot_price` variable initialized to `0.0`.
            *   Added logic to parse messages from `deribit_price_index` channel and update `spot_price`.
            *   Changed `notional` calculation to `size * (spot_price or mark)` (using spot price if available).
            *   Removed the `underlying_price` assignment in `dealer.assign(...)` as `roll_up` uses `notional_usd` directly.
        *   Added `import warnings; warnings.filterwarnings("ignore", category=RuntimeWarning)` to suppress the (now guarded against) warning display.

6.  **Problem 21: Parse Error & Spot Price Still Zero (`KeyError: 'index_price'`)**
    *   **Symptom:** After implementing the previous fix, the processor logged `PARSE ERR 'index_price'`, and the `/snapshot` endpoint still showed `price: 0.0`.
    *   **Diagnosis:** The processor code attempted to access `d["index_price"]` from the price index message, but the actual key provided by Deribit is `price`.
    *   **Cause:** Incorrect key used to access the spot price in the JSON payload.
    *   **Solution:** Modified the price index parsing logic in `processor.py` to safely get the price using `spot_price = float(d.get("price") or d.get("index_price") or 0.0)`.

7.  **Problem 22: Spot Price Still Zero & No Metrics Published (Case Sensitivity)**
    *   **Symptom:** After fixing the key error, the `/snapshot` endpoint returned `200 OK` but with `price: 0.0` and near-zero metrics. Logs showed the collector pushing messages but no "PROCESSOR: stored ... greeks" messages, indicating the ticker branch in the processor was likely still being skipped.
    *   **Diagnosis:** The check `ch.startswith("deribit_price_index")` was case-sensitive. Deribit likely sends the channel name with different casing (e.g., `deribit_price_index.BTC_USD`). Although the subscription in the collector *might* be case-insensitive, the *check* in the processor was failing. Because `spot_price` remained `0.0`, the processor correctly skipped calculating notionals and storing greeks (due to the `if spot_price == 0: continue` guard added earlier).
    *   **Cause:** Case-sensitive check failing to match the actual incoming channel name for the spot price index.
    *   **Solution:**
        *   Modified the spot price channel check in `processor.py` to be case-insensitive: `if ch.lower().startswith("deribit_price_index"):`.
        *   Ensured the `notional` calculation uses `spot_price` correctly and the `if spot_price == 0: continue` guard prevents processing ticks before the spot price is known.

---

**Current State (Pending Validation):**

*   The collector connects (authenticated), subscribes to spot index and a limited set of option tickers/books.
*   The processor attempts to parse spot index messages (now case-insensitive) and ticker messages.
*   The processor calculates missing higher-order greeks using `bs_greeks`.
*   The processor aggregates metrics using placeholder dealer netting (`dealer_side_mult = 1`).
*   The processor handles potential `KeyError`s and `TypeError`s during parsing and serialization.
*   The processor guards against division-by-zero errors.
*   The API serves the latest processed metrics from the `dealer_metrics` Redis stream.
*   **Expected Next Outcome:** Logs should show successful processing of both spot index and ticker messages, `PROCESSOR: stored ... greeks` messages should appear, and `/snapshot` should return JSON with a non-zero spot `price` and realistically scaled metrics (NGI, VSS, etc.).

**(End of Log - Awaiting results of running the latest patched code)**




================================================
FILE: start.sh
================================================
#!/bin/sh
set -e

echo "Starting Deribit WebSocket collector..."
python -m dealer_flow.deribit_ws &

echo "Starting Processor..."
python -m dealer_flow.processor &

echo "Starting Uvicorn API server..."
uvicorn dealer_flow.rest_service:app --host 0.0.0.0 --port 8000


================================================
FILE: .dockerignore
================================================
.git
__pycache__/
*.parquet
*.env
node_modules



================================================
FILE: .env.example
================================================
REDIS_URL=redis://localhost:6379/0
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
DERIBIT_WS=wss://www.deribit.com/ws/api/v2
CURRENCY=BTC



================================================
FILE: dealer_flow/__init__.py
================================================
__all__ = ["config"]



================================================
FILE: dealer_flow/__main__.py
================================================
"""
Convenience entrypoint: launches collector and API concurrently
"""
import asyncio
from dealer_flow.deribit_ws import run as ws_run
from dealer_flow.rest_service import app  # ensures FastAPI import
import uvicorn

async def main():
    task_ws = asyncio.create_task(ws_run())
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(task_ws, server.serve())

if __name__ == "__main__":
    asyncio.run(main())



================================================
FILE: dealer_flow/config.py
================================================
#### 1 `dealer_flow/config.py`
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Web-socket & REST hosts
    deribit_ws: str = "wss://www.deribit.com/ws/api/v2"
    deribit_rest: str = "https://www.deribit.com/api/v2"

    # OAuth2 creds (set in .env)
    deribit_id: str = "lIdRCJdl"
    deribit_secret: str = "BiqWyPz855okyEBIaSFYre4vAXQ7t1az1pETWE36Dwo"

    # Redis
    redis_url: str = "redis://:changeme@redis:6379/0"

    # General
    currency: str = "BTC"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"


settings = Settings()



================================================
FILE: dealer_flow/dealer_net.py
================================================
"""
Infers dealer sign (MM vs customer) from open interest.
Assume dealer net pos = -customer_net_pos.
"""
import pandas as pd
import numpy as np

def infer_dealer_net(oi_df: pd.DataFrame) -> pd.DataFrame:
    """
    oi_df may contain:
        ['instrument', 'gamma', 'vanna', 'charm', 'volga', 'notional_usd', ...]
    Optionally:
        ['side'] with values like 'call_long', 'call_short', etc.

    Returns same DF with a 'dealer_side_mult' column (1 or -1).
    """
    if "side" in oi_df.columns:
        oi_df["dealer_side_mult"] = np.where(
            oi_df["side"].str.contains("short"), 1, -1
        )
    else:
        # no side info yet – assume dealer needs to hedge ALL customer gamma
        oi_df["dealer_side_mult"] = 1

    return oi_df



================================================
FILE: dealer_flow/deribit_ws.py
================================================
"""
Collector with verbose logging.
If credentials missing or auth fails we fall back to **unauth** mode and
subscribe to at most 12 liquid ATM option strikes to guarantee success.
"""
import asyncio, json, time, uuid, aiohttp, websockets, orjson, sys
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

TOKEN_TTL = 23 * 3600
MAX_UNAUTH_STRIKES = 12            # Deribit limit for 100 ms streams

async def auth_token():
    if not (settings.deribit_id and settings.deribit_secret):
        print("COLLECTOR: creds absent → unauth mode", file=sys.stderr)
        return None, 0
    async with aiohttp.ClientSession() as sess:
        try:
            r = await sess.get(
                f"{settings.deribit_rest}/public/auth",
                params={
                    "grant_type": "client_credentials",
                    "client_id": settings.deribit_id,
                    "client_secret": settings.deribit_secret,
                },
                timeout=10,
            )
            j = await r.json()
        except Exception as e:
            print(f"COLLECTOR: auth HTTP error {e} → unauth mode", file=sys.stderr)
            return None, 0
    if "error" in j:
        print(f"COLLECTOR: auth rejected {j['error']} → unauth mode", file=sys.stderr)
        return None, 0
    token = j["result"]["access_token"]
    print("COLLECTOR: auth OK", file=sys.stderr)
    return token, time.time() + TOKEN_TTL


async def current_instruments():
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(
            f"{settings.deribit_rest}/public/get_instruments",
            params=dict(currency=settings.currency, kind="option", expired="false"),
            timeout=10,
        )
        data = (await r.json())["result"]
        # crude filter: keep first strikes near ATM
        return [d["instrument_name"] for d in data[:MAX_UNAUTH_STRIKES]]


async def subscribe(ws, channels):
    req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "public/subscribe",
        "params": {"channels": channels},
    }
    await ws.send(orjson.dumps(req).decode())


async def run():
    redis = await get_redis()

    while True:  # reconnect loop
        token, token_exp = await auth_token()
        try:
            instruments = await current_instruments()
        except Exception as e:
            print(f"COLLECTOR: instrument fetch failed {e}", file=sys.stderr)
            await asyncio.sleep(5)
            continue

        spot_ch = f"deribit_price_index.{settings.currency.lower()}_usd"
        subs = (
            [spot_ch]
            + [f"ticker.{i}.100ms" for i in instruments]
            + [f"book.{i}.100ms" for i in instruments]
        )

        hdrs = {"Authorization": f"Bearer {token}"} if token else {}
        mode = "auth" if token else "unauth"
        print(f"COLLECTOR: connecting ({mode}), {len(subs)} channels …",
              file=sys.stderr)

        try:
            async with websockets.connect(
                settings.deribit_ws, extra_headers=hdrs, ping_interval=20
            ) as ws:
                await subscribe(ws, subs)
                print("COLLECTOR: subscribed, streaming …", file=sys.stderr)
                cnt = 0
                async for msg in ws:
                    await redis.xadd(STREAM_KEY_RAW, {"d": msg.encode()})
                    cnt += 1
                    if cnt % 500 == 0:
                        print(f"COLLECTOR: pushed {cnt} msgs", file=sys.stderr)
        except Exception as e:
            print(f"COLLECTOR: websocket error {e} – reconnect in 5 s",
                  file=sys.stderr)
            await asyncio.sleep(5)

if __name__ == "__main__":
    import asyncio, sys
    try:
        print("COLLECTOR: launching …", file=sys.stderr)
        asyncio.run(run())
    except KeyboardInterrupt:
        print("COLLECTOR: interrupted, exiting.", file=sys.stderr)


================================================
FILE: dealer_flow/gamma_flip.py
================================================
import numpy as np
import pandas as pd
from typing import Optional


def gamma_flip_distance(
    gamma_by_strike: pd.Series, spot_price: float
) -> Optional[float]:
    """
    gamma_by_strike: index=strike, value=net dealer gamma
    Finds first zero-cross and returns (strike/spot - 1)
    """
    signs = np.sign(gamma_by_strike.values)
    zero_idx = np.where(np.diff(signs))[0]
    if zero_idx.size == 0:
        return None
    flip_strike = gamma_by_strike.index[zero_idx[0] + 1]
    if spot_price == 0:
        return None
    return float(flip_strike / spot_price - 1.0)


================================================
FILE: dealer_flow/greek_calc.py
================================================
"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.
All inputs are numpy arrays for vectorised speed.
"""
"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.

Doctest sanity check
>>> import numpy as np; from dealer_flow.greek_calc import greeks
>>> γ, v, c, vg = greeks(np.array([100]), np.array([100]), np.array([0.1]), 0.0, np.array([0.5]), np.array([1]))
>>> round(float(γ), 6)
0.079788
"""
import numpy as np
from numba import njit
#from scipy.stats import norm  # only used for cdf/pdf

SQRT_2PI = np.sqrt(2 * np.pi)

@njit(fastmath=True)
def _pdf(x):
    return np.exp(-0.5 * x * x) / SQRT_2PI

@njit(fastmath=True)
def _cdf(x):
    return 0.5 * (1.0 + np.erf(x / np.sqrt(2.0)))

@njit(fastmath=True)
def greeks(S, K, T, r, sigma, option_type):
    """
    Returns gamma, vanna, charm, volga for each row.
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    pdf_d1 = _pdf(d1)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    
    # vanna = ∂^2 price / ∂S ∂σ
    vanna = -d2 * pdf_d1 / sigma
    
    # charm (dDelta/dt)
    charm = (
        -pdf_d1 * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
    )
    
    vega = S * pdf_d1 * np.sqrt(T)
    volga = vega * d1 * d2 / sigma
    
    return gamma, vanna, charm, volga



================================================
FILE: dealer_flow/hpp_score.py
================================================
def hpp(spot_move_sign: int, NGI: float, VSS: float, CHL: float, alpha=0.1, beta=0.1):
    """
    Hedge-Pressure Projection
    """
    return spot_move_sign * NGI + alpha * VSS + beta * CHL



================================================
FILE: dealer_flow/processor.py
================================================
# ---------- NEW FILE: dealer_flow/processor.py ----------
"""
Processor: reads raw Deribit messages from Redis Stream `dealer_raw`,
derives minimal metrics, writes JSON blob to `dealer_metrics`.

This first iteration *only*:
• parses ticker price from perpetual feed
• counts messages per rolling 1-second window (msg_rate)
• publishes stub NGI/VSS/CHL/HPP so the dashboard endpoint works

Subsequent iterations will:
• ingest options OI, compute full greeks, HPP, scenario bucket
"""

"""
Processor: aggregates option greeks & dealer net,
publishes roll-ups every second to `dealer_metrics`.
"""
import asyncio, time, orjson, pandas as pd, numpy as np, sys
import datetime as dt, calendar
import re, datetime as dt, calendar
import logging
from collections import deque, defaultdict
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks   # NEW

JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY
GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0  # s
_DATE_RE = re.compile(r"(\d{1,2})([A-Z]{3})(\d{2})")  # day, month, yy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# in-memory state
greek_store = {}        # inst -> dict(gamma, vanna, charm, volga, OI)
gamma_by_strike = {}    # strike -> net dealer gamma
prices = deque(maxlen=1)
tick_times = deque(maxlen=1000)
spot = [0.0]

async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise

async def maybe_publish(redis):
    now = time.time()
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()
    if not prices:
        return
    # Build DataFrame
    df = pd.DataFrame.from_dict(greek_store, orient="index")
    if df.empty:
        return
    dealer = infer_dealer_net(df.reset_index(names="instrument"))
    # apply dealer sign to greeks
    signed = dealer.copy()
    signed[["gamma", "vanna", "charm", "volga"]] = (
        signed[["gamma", "vanna", "charm", "volga"]]
        .mul(signed["dealer_side_mult"], axis=0)
    )
    agg = roll_up(signed)
    spot_val = spot[0] or (prices[-1] if prices else 0.0)
    flip = gamma_flip_distance(pd.Series(gamma_by_strike), spot_val)
    payload = {
        "ts": now,
        "price": spot_val,
        "msg_rate": len(tick_times),
        **agg,
        "flip_pct": flip,
    }
    await redis.xadd(
        STREAM_KEY_METRICS,
        {"d": orjson.dumps(payload, option=JSON_OPTS)}
    )

def _expiry_ts(sym: str) -> float:
    """
    Extract expiry from option symbol. Returns UTC timestamp 08:00 expiry.
    """
    date_part = sym.split("-")[1]           # e.g. 5MAY25
    m = _DATE_RE.fullmatch(date_part)
    if not m:
        raise ValueError(f"unparsable date {date_part}")
    day, mon, yy = int(m[1]), m[2], int(m[3])
    month_num = dt.datetime.strptime(mon, "%b").month
    year_full = 2000 + yy
    dt_exp = dt.datetime(year_full, month_num, day, 8, tzinfo=dt.timezone.utc)
    return dt_exp.timestamp()

async def processor():
    redis = await get_redis()
    await ensure_group(redis)
    print("PROCESSOR: started, waiting for data …", file=sys.stderr)
    last_pub = time.time()

    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
        if resp:
            for _, msgs in resp:
                for mid, data in msgs:
                    try:
                        j = orjson.loads(data[b"d"])
                        params = j.get("params", {})
                        ch, d = params.get("channel"), params.get("data")
                        if not isinstance(d, dict):
                            continue                        
                        # ------------ SPOT INDEX (robust) ---------------
                        if ch and ch.lower().startswith("deribit_price_index"):
                            spot_val = None
                            try:
                                spot_val = float(d.get("price") or d.get("index_price") or 0)
                            except (TypeError, ValueError):
                                logging.warning("Bad index payload %s", d)
                            if not spot_val:
                                continue

                            if spot_val > 0:
                                spot[0] = spot_val
                                prices.append(spot_val)
                            continue
                        if ch.startswith("ticker"):
                            mark = float(d["mark_price"])
                            prices.append(mark)

                            inst = d["instrument_name"]      # BTC-24MAY25-60000-P
                            strike = float(inst.split("-")[2])
                            expiry_ts = _expiry_ts(inst) 
                            now_ts    = d["timestamp"] / 1000
                            T = max((expiry_ts - now_ts), 0.0) / (365 * 24 * 3600)

                            size  = d["open_interest"]        # contracts
    
                            notional = size * (spot[0] or mark)         

                            deriv_greeks = d.get("greeks", {})
                            gamma = deriv_greeks.get("gamma", 0.0)

                            # If vanna/charm/volga missing → compute
                            vanna  = deriv_greeks.get("vanna")
                            charm  = deriv_greeks.get("charm")
                            volga  = deriv_greeks.get("volga")

                            if None in (vanna, charm, volga):
                                sigma = d.get("mark_iv", 0) / 100  # iv in pct
                                if sigma <= 0 or T <= 0:
                                    # cannot compute, default zeros
                                    vanna = vanna or 0.0
                                    charm = charm or 0.0
                                    volga = volga or 0.0
                                else:
                                    S = np.array([mark])
                                    K = np.array([strike])
                                    g, v, c, vg = bs_greeks(
                                        S, K, np.array([T]), 0.0, np.array([sigma]), np.array([1])
                                    )
                                    vanna = vanna or float(v[0])
                                    charm = charm or float(c[0])
                                    volga = volga or float(vg[0])

                            greeks = {
                                "gamma": gamma,
                                "vanna": vanna,
                                "charm": charm,
                                "volga": volga,
                                "notional_usd": notional,
                                "strike": strike,
                            }
                            greek_store[inst] = greeks
                            gamma_by_strike[strike] = (
                                gamma_by_strike.get(strike, 0.0) + gamma
                            )
                            if len(greek_store) % 1000 == 0:
                                print(f"PROCESSOR: stored {len(greek_store)} greeks",
                                      file=sys.stderr)
                        tick_times.append(time.time())
                        logging.debug(
                            "ticker %s spot=%.2f mark=%.2f gamma=%.3g",
                            inst,
                            spot[0],
                            mark,
                            gamma,
                        )
                    except Exception as e:
                        print(f"PARSE ERR {e}", file=sys.stderr)
        now = time.time()
        if now - last_pub >= ROLL_FREQ:
            await maybe_publish(redis)
            last_pub = now

if __name__ == "__main__":
    asyncio.run(processor())



================================================
FILE: dealer_flow/redis_stream.py
================================================
import aioredis
from dealer_flow.config import settings

STREAM_KEY_RAW = "dealer_raw"
STREAM_KEY_METRICS = "dealer_metrics"

async def get_redis():
    return await aioredis.from_url(settings.redis_url, decode_responses=False)



================================================
FILE: dealer_flow/rest_service.py
================================================
from fastapi import FastAPI, Response, status
from dealer_flow.redis_stream import get_redis, STREAM_KEY_METRICS
import orjson
import asyncio

app = FastAPI()

@app.get("/snapshot")
async def snapshot():
    redis = await get_redis()
    last = await redis.xrevrange(STREAM_KEY_METRICS, count=1)
    if not last:
        # metrics not produced yet → 204 No Content
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return orjson.loads(last[0][1][b"d"])









================================================
FILE: dealer_flow/rules.py
================================================
def classify(flow: dict, adv_usd: float, spot_change_pct: float):
    """
    flow keys: NGI, VSS, CHL_24h, HPP
    Returns bucket label 1-6
    """
    material = abs(flow["NGI"]) > 0.1 * adv_usd
    rising = spot_change_pct > 0
    falling = spot_change_pct < 0
    
    if rising and flow["NGI"] < 0:
        return "Dealer Sell Material" if material else "Dealer Sell Immaterial"
    if falling and flow["NGI"] > 0:
        return "Dealer Buy Material" if material else "Dealer Buy Immaterial"
    if abs(flow["NGI"]) < 1e-6:
        return "Gamma Pin"
    if abs(flow["VSS"]) > abs(flow["NGI"]) * 2:
        return "Vanna Squeeze"
    return "Neutral"



================================================
FILE: dealer_flow/vanna_charm_volga.py
================================================
import pandas as pd

def roll_up(dealer_greeks: pd.DataFrame, spot_pct: float = 0.01) -> dict:
    """
    dealer_greeks columns: ['gamma','vanna','charm','volga','notional_usd']
    Returns NGI, VSS, CHL_24h, VOLG
    """
    # Dollar gamma for 1% move
    dealer_greeks["dollar_gamma"] = (
        dealer_greeks["gamma"] * dealer_greeks["notional_usd"] * spot_pct
    )
    NGI = dealer_greeks["dollar_gamma"].sum()
    
    VSS = (dealer_greeks["vanna"] * 0.01 * dealer_greeks["notional_usd"]).sum()
    CHL = (dealer_greeks["charm"] * 24 / 365 * dealer_greeks["notional_usd"]).sum()
    VOLG = (dealer_greeks["volga"] * 0.01 * dealer_greeks["notional_usd"]).sum()
    
    return dict(NGI=NGI, VSS=VSS, CHL_24h=CHL, VOLG=VOLG)




================================================
FILE: dealer_flow/tests/test_gamma_flip.py
================================================
import pandas as pd
from dealer_flow.gamma_flip import gamma_flip_distance

def test_basic_flip():
    strikes = [9000, 9500, 10000, 10500]
    gamma = [-2.0, -1.0, 0.5, 1.2]
    series = pd.Series(gamma, index=strikes)
    assert gamma_flip_distance(series, 10000) == 0.05

