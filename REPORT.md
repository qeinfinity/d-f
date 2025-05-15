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


## Dealer-Flow Stack: Troubleshooting Log & Maintainer Guide (Continuation)

**Previous State:** The processor was logging `PARSE ERR local variable 'spot_val' referenced before assignment` for initial ticks, and metrics VSS, CHL_24h, VOLG were zero in the `/snapshot` output. The "PROCESSOR: stored ... greeks" log was not appearing.

---

**Phase 7: Refining Processor Logic & Finalizing MVP Metrics**

1.  **Problem 23: `spot_val` UnboundLocalError in Ticker Logging & VSS/CHL/VOLG Zeros**
    *   **Symptom (User Confirmed):** Initial `PARSE ERR local variable 'spot_val' referenced before assignment` errors appeared, followed by `PROCESSOR: ticker ...` logs showing the correct spot price. The `/snapshot` endpoint returned data with `price`, `NGI`, `flip_pct` populated, but `VSS`, `CHL_24h`, `VOLG` were `0.0`. The `PROCESSOR: stored ... greeks` log was not appearing.
    *   **Diagnosis (System Analysis):**
        *   **`spot_val` Logging Error:** The debug print statement `print(f"PROCESSOR: ticker {inst} spot={spot_val}", file=sys.stderr)` inside the *ticker processing block* (`if ch.startswith("ticker"):`) correctly used the *local* `spot_val` (which was only defined in the *price index* block: `if ch and ch.lower().startswith("deribit_price_index"):`). When a ticker message arrived *before* any price index message, this local `spot_val` was indeed unassigned in the ticker block's scope, leading to the `UnboundLocalError` caught by the general `except Exception as e:`. Once a price index message arrived, the *global* `spot = [0.0]` was updated. Subsequent ticker messages *would* have failed if they tried to use a local `spot_val`. The provided diff correctly changed the `spot_price` variable (used for the global `spot` list) to `spot_val` locally *within the spot index branch only*. The debug print in the ticker branch should use the global `spot[0]`.
        *   **Zero VSS/CHL/VOLG:** The `processor.py` logic: `vanna = deriv_greeks.get("vanna")` (and similar for charm, volga) would assign `None` if these keys weren't in Deribit's payload (which they aren't for standard ticker messages). The subsequent `if None in (vanna, charm, volga):` block *correctly* triggered the fallback to `bs_greeks`. However, the `else:` block inside this condition (which would assign `vanna = vanna or 0.0`) was only hit if `sigma <= 0 or T <= 0`. If `sigma` and `T` *were* valid, but `bs_greeks` returned, say, `v[0]` as a non-None value (e.g., a valid float), then `vanna = vanna or float(v[0])` would evaluate to `vanna = None or <calculated_float>`, resulting in `vanna = <calculated_float>`. The issue wasn't that they were *always* zero, but that the `/snapshot` might have been hit when `greek_store` was still small, and perhaps those initial items had `sigma` or `T` as zero, or `bs_greeks` legitimately calculated zero for those specific inputs. The core logic to calculate them was present.
        *   **Missing "stored greeks" log:** This was due to a combination of the `MAX_UNAUTH_STRIKES = 12` in `deribit_ws.py` (limiting the number of unique instruments) and the `if len(greek_store) % 1000 == 0:` threshold. The system simply wasn't processing 1000 unique instruments quickly enough with the limited subscription set.
    *   **Cause:** Scoping error in a debug print statement. Greeks defaulting to zero under certain initial conditions or if `bs_greeks` calculates zero. High threshold for a progress log.
    *   **Solution (Applied in Patches & Analysis):**
        *   The `spot_val` print issue was addressed by changing the debug print to `logging.debug("ticker %s spot=%.2f mark=%.2f gamma=%.3g", inst, spot[0], mark, gamma)`. This uses the global `spot[0]`.
        *   The VSS/CHL/VOLG zeros were not due to a fundamental flaw in *not* calling `bs_greeks`, but rather that `bs_greeks` *was* being called, and for initial ticks or certain parameter combinations, it could legitimately return zero, or the `mark_iv`/`T` could be zero, leading to the `0.0` defaults. The patch provided by the system (which you confirmed by applying your full `processor.py`) ensured that `vanna`, `charm`, `volga` are *always* assigned the result of `bs_greeks` if they were initially `None` and if `sigma` and `T` are valid:
            ```python
            # ...
            if None in (vanna, charm, volga):
                sigma = d.get("mark_iv", 0) / 100
                if sigma <= 0 or T <= 0:
                    vanna = vanna or 0.0 # If already None, becomes 0.0
                    charm = charm or 0.0
                    volga = volga or 0.0
                else:
                    # ... bs_greeks calculation ...
                    vanna = float(v[0]) # Direct assignment, not "vanna or float(v[0])"
                    charm = float(c[0])
                    volga = float(vg[0])
            # ...
            ```
            This change ensures `vanna`, `charm`, `volga` are populated with the calculated values from `bs_greeks` when inputs are valid, rather than potentially remaining `0.0` if their `deriv_greeks.get()` was `None` but `bs_greeks` would have produced a non-zero result.
        *   The "stored greeks" log threshold was recommended to be lowered (e.g., to `% 100`) for better visibility during testing with limited instruments.

2.  **Problem 23 (Cont.): Implementing Full Greek Roll-up for Milestone 2**
    *   **Context:** `/snapshot` now returned price, NGI, and flip_pct, but VSS, CHL_24h, and VOLG were still 0.0. The next step was to fully implement Milestone 2.
    *   **User Action:** The user confirmed readiness to implement the "Road-map to Milestone 2 'Full Greek Roll-up' spec."
    *   **Diagnosis (System Analysis):** The system identified that VSS/CHL/VOLG were zero because the `bs_greeks` calculation (triggered when Deribit doesn't provide these greeks) might still result in zeros for initial ticks if `mark_iv` or Time-to-Expiry (`T`) were zero or invalid. The key was to ensure that `vanna`, `charm`, and `volga` in the `greeks` dictionary are *always* populated from the output of `bs_greeks` when Deribit doesn't supply them and when inputs to `bs_greeks` (S, K, T, r, sigma) are valid. Additionally, the HPP and scenario classification were missing from the payload.
    *   **Solution (Provided as a diff by the system):**
        *   **`dealer_flow/vanna_charm_volga.py`:** Corrected the scaling for `VSS` and `VOLG` to use `spot_pct` (consistent with NGI if NGI represents a % move sensitivity) and clarified comments.
        *   **`dealer_flow/processor.py`:**
            *   Imported `hpp_score` and `rules`.
            *   Added `last_pub_price = [0.0]` global to track spot price changes for `spot_move_sign`.
            *   In `maybe_publish()`:
                *   Calculated `spot_move_sign`.
                *   Called `hpp_score.hpp(...)` to get `HPP_val`.
                *   Called `rules.classify(...)` to get `scenario`.
                *   Added `HPP` and `scenario` to the payload.
                *   Updated `last_pub_price[0] = spot_val`.
            *   In the ticker processing block: Ensured `gamma` defaults to `0.0` if missing. Crucially, ensured that if `vanna`, `charm`, or `volga` are `None` (i.e., not provided by Deribit), they are *directly assigned* the calculated values from `bs_greeks` (e.g., `vanna = float(v[0])`) rather than `vanna = vanna or float(v[0])`, which would keep them as `0.0` if they were initialized to `0.0` and `bs_greeks` returned `0.0`.
    *   **Current Unsolved State (as per last user log):**
        *   The logs `PARSE ERR local variable 'spot_val' referenced before assignment` are still appearing for the initial few messages.
        *   The "PROCESSOR: stored ... greeks" message is not appearing, but "COLLECTOR: pushed ... msgs" is.
        *   The `/snapshot` endpoint *is* returning `200 OK` with a JSON payload that includes `price`, `NGI`, `VSS`, `CHL_24h`, `VOLG`, and `flip_pct`. However, while `price`, `NGI`, and `flip_pct` seem to have reasonable values (e.g., `price: 96050.38`), the `VSS`, `CHL_24h`, and `VOLG` are still `0.0`. This indicates that either the conditions `sigma <= 0 or T <= 0` are frequently true for the initial set of instruments, or `bs_greeks` is legitimately calculating zeros for these higher-order greeks based on the initial market data, or the `greeks` dictionary update from `bs_greeks` output is not correctly populating these values before they are summed in `roll_up`.

---

**(End of Log - Awaiting resolution for Problem 23 (Cont.): Zero VSS/CHL/VOLG despite `bs_greeks` call, and persistent `spot_val` UnboundLocalError in initial logs. The "PROCESSOR: stored ... greeks" log also remains elusive.)**


**Previous State:** The processor was logging `PARSE ERR local variable 'spot_val' referenced before assignment` for initial ticks. Metrics VSS, CHL_24h, VOLG were zero in the `/snapshot` output. The "PROCESSOR: stored ... greeks" log was not appearing, primarily due to a combination of a limited instrument set (MAX\_UNAUTH\_STRIKES = 12) and a high logging threshold.

---

**Phase 7: Refining Processor Logic & Achieving Full Greek Roll-up (Continued)**

*   **Problem 23 (Cont.): Zero VSS/CHL/VOLG, Missing "stored greeks" Log, and Initial `spot_val` Errors**
    *   **Symptom (Previous Snapshot & Logs):** While `price`, `NGI`, and `flip_pct` might have shown values, `VSS`, `CHL_24h`, and `VOLG` were stubbornly `0.0`. The informative "PROCESSOR: stored ... greeks" log was absent. Initial logs sometimes showed `PARSE ERR local variable 'spot_val' referenced before assignment`.
    *   **Diagnosis & Solution Path (Recap of Critical System-Wide Changes Implemented):**
        1.  **Expanded Instrument Subscription (`deribit_ws.py`):** The collector was overhauled.
            *   Authentication (`auth_token`) was made robust.
            *   `current_instruments()` was modified to fetch the full list of options from Deribit when authenticated, and then subscribe to `settings.deribit_max_auth_instruments` (e.g., 100 or 150 as per `.env` via `config.py`). The faulty `open_interest` sort against the `/public/get_instruments` endpoint (which lacks live OI) was removed, unblocking the subscription to a larger instrument set.
            *   Logging was significantly enhanced to trace authentication and instrument selection.
        2.  **Spot Price Handling (`processor.py`):**
            *   The global `spot = [0.0]` is now reliably updated by the `deribit_price_index` channel, with case-insensitive matching for the channel name.
            *   The `current_underlying_price` for notional and Black-Scholes calculations correctly uses `spot[0]` (falling back to option `mark_price` only if `spot[0]` is still `0.0`).
            *   The transient `spot_val` `UnboundLocalError` in early logs was primarily a debug-print artifact; core logic now correctly uses the global `spot[0]`.
        3.  **Black-Scholes Integration for Higher-Order Greeks (`processor.py`):**
            *   The `bs_greeks` function is now correctly called when Deribit's ticker feed does *not* provide `vanna`, `charm`, or `volga`.
            *   **Crucial Fix:** Values from `bs_greeks` (`v[0]`, `c[0]`, `vg[0]`) are *directly assigned* to `vanna`, `charm`, `volga` respectively if the Deribit-provided values were `None` and if `sigma` (from `mark_iv`) and `T` (Time to Expiry) are valid. This ensures that calculated greeks populate these fields.
            *   The underlying spot price (`current_underlying_price`) is used as the `S` parameter for `bs_greeks`.
            *   Option type (Call/Put) is correctly inferred for `bs_greeks`.
        4.  **Metrics Payload Enrichment (`processor.py` & `vanna_charm_volga.py`):**
            *   `hpp_score.hpp` and `rules.classify` are now integrated into `maybe_publish`.
            *   `HPP` and `scenario` are included in the `/snapshot` payload.
            *   The `CHL_24h` calculation in `vanna_charm_volga.py` was corrected to use `* (1 / 365.0)`.
            *   VSS and VOLG calculations in `vanna_charm_volga.py` were clarified to represent a 1% IV change.
        5.  **Logging Threshold (`processor.py`):** The threshold for the "PROCESSOR: Stored greeks for..." log (`LOG_STORE_THRESHOLD`) was lowered (e.g., to 5 or 10) during development, enabling earlier confirmation of greek storage with the expanded instrument set.
    *   **Outcome (Reflected in User's Latest `/snapshot`):**
        *   The `/snapshot` endpoint now returns **non-zero, dynamically changing values** for `NGI`, `VSS`, `CHL_24h`, and `VOLG`, alongside `price`, `HPP`, and `scenario`. This signifies successful calculation and aggregation of all primary greeks across a larger set of instruments.
        *   Logs confirm "COLLECTOR: auth OK" and successful subscription to a larger number of instruments (e.g., "PROCESSOR: Stored greeks for 100 instruments..." messages appear regularly).
        *   Milestone 2 ("Full Greek Roll-up") is now **substantially MET.**

---

**Phase 8: Validating Milestone 2 Completion & Addressing Final Polish**

*   **Problem 24: `flip_pct: null` in `/snapshot`**
    *   **Symptom:** Despite other metrics being live, `flip_pct` consistently shows `null`.
    *   **Diagnosis:** The `gamma_flip_distance` function returns `None` if it doesn't find a strike where the aggregate dealer-netted gamma (`current_gamma_by_strike`) changes sign.
    *   **Cause:** For the currently subscribed set of instruments (e.g., top 100 by Deribit's default sort, not necessarily by OI or a full ATM + wings spread), the collective gamma profile across their strikes might be consistently positive or negative. A `null` value is a valid output if no such "flip point" exists within the observed range.
    *   **Verification & Next Steps:**
        1.  **Logging:** Add detailed logging within `gamma_flip.py` to output the `gamma_by_strike.sort_index()` series and the `spot_price` it receives. This will confirm the exact input data. Also, log `current_gamma_by_strike` in `processor.py`'s `maybe_publish` just before calling `gamma_flip_distance`.
        2.  **Interpretation:** A `null` `flip_pct` is a piece of information in itself – it means, for the observed slice of the market, there's no imminent strike where gamma exposure flips sign.
        3.  **Future Enhancement (Instrument Selection):** To increase the chance of observing a flip, future instrument selection logic could aim for broader strike coverage or specifically target strikes around known high OI areas.
        4.  **Dashboard Handling:** The UI should gracefully display "N/A" or similar when `flip_pct` is `null`.

*   **Problem 25 (Minor/Resolved): Initial `PARSE ERR local variable 'spot_val' referenced before assignment` logs**
    *   **Symptom:** Previously observed for the very first few messages if a ticker message arrived before the first spot price update.
    *   **Status:** This was largely a transient debug-logging artifact. The core logic in `processor.py` now robustly uses the global `spot[0]` (updated by the spot index channel) and correctly falls back to `mark_price` if `spot[0]` is zero during initial `notional` calculations: `current_underlying_price = spot[0] or mark_price`. This issue is considered **mitigated/resolved** for sustained operation.

---

**Review of Previously Identified Core Concerns (Post-Phase 8 Validation):**

1.  **Dealer Netting Simplification (`dealer_net.py`):**
    *   **Status:** Remains a **Known Limitation.** `dealer_side_mult` is effectively `1` for all instruments. The system calculates "gross potential dealer exposure." *This fulfills the letter of Milestone 2 by calculating greeks, but true dealer flow nuance is a future step.*
2.  **Raw Gamma for Flip Point (`gamma_flip.py`, `processor.py`):**
    *   **Status:** The mechanism now uses the *signed* gamma from the `signed` DataFrame (which currently means raw gamma due to point 1). **Functionally Solved** based on current capabilities.
3.  **CHL\_24h (Charm Load) Scaling (`vanna_charm_volga.py`):**
    *   **Status:** **Solved.** Formula is `* (1 / 365.0)`.
4.  **Scenario `adv_usd` Placeholder (`processor.py`, `rules.py`):**
    *   **Status:** Remains a **Known Limitation/Placeholder.** Classification uses a heuristic based on observed notional.
5.  **Limited Instrument Set (`deribit_ws.py`):**
    *   **Status:** **Solved.** The collector subscribes to `settings.deribit_max_auth_instruments`, providing a significantly broader data set than the initial 12.

**Alignment with Project Scope v0.3 & Milestones (Post-Phase 8 Validation):**

*   **Mission:**
    1.  `Quantifies dealer hedge pressure (gamma, vanna, charm, volga)`: **ACHIEVED.** Live, non-zero metrics are being produced for a broad set of instruments. (Acknowledging European greeks for Asian options as per `ASIAN_CALC.md`, and simplified netting).
    2.  `Flags flow-driven regime states`: **ACHIEVED.** The `scenario` field (e.g., "Vanna Squeeze") is live.
    3.  `Feeds ... dashboard and ... model sleeve`: The `/snapshot` endpoint **IS THE LIVE FEED.**

*   **Deliverables & Milestones:**
    *   `1. MVP Wire-up`: **DONE.**
    *   `2. Full Greek Roll-up`: **MET!**
        *   `option feed auth`: **DONE.**
        *   `filtered strike set`: **DONE** (subscribes to `deribit_max_auth_instruments` instruments, a significant improvement).
        *   `NGI/VSS/CHL/VOLG live`: **DONE!** (Confirmed by `/snapshot` output). HPP and scenario are also live.

**Path Forward: Onwards to Dashboard & Beyond!**

With Milestone 2 robustly achieved, the path is clear:

1.  **Dashboard v1 (Milestone 3):**
    *   Design and implement the Plotly Dash application.
    *   Visualize key metrics from `/snapshot`: Spot price (sparkline), NGI, VSS, CHL_24h, VOLG, HPP (gauges/meters), Scenario (badge), `flip_pct`.
    *   Develop the `/heatmap` API endpoint: The processor will need to periodically push aggregated greek data (e.g., `greek_store` or a derivative, grouped by strike/expiry) to a new Redis key/stream for this endpoint to consume.
2.  **Historical Backfill (Milestone 4):**
    *   Implement ClickHouse schema.
    *   Build a separate script/service to consume `dealer_metrics` from Redis and persist to ClickHouse.
    *   Address 30-day options/OI ingestion (this might require historical data fetching from Deribit if not captured live from day 1 of ClickHouse deployment).
3.  **Systematic Sleeve & Hardening (Milestones 5 & 6):** These will build upon the live data and historical persistence.
4.  **Addressing Known Limitations & Future Enhancements (Post v0.3 MVP):**
    *   **Sophisticated Dealer Netting:** Top priority for improving signal quality.
    *   **Asian Option Adjustments:** Especially for near-expiry options.
    *   **Dynamic ADV & Thresholds:** For more adaptive scenario classification and HPP.
    *   **Expanded Data Sources:** Block trades, OTC data, CME data for a holistic market view.
    *   **Advanced Instrument Selection:** OI-prioritized selection, dynamic subscriptions.

The current state, with a functioning `/snapshot` delivering rich, live dealer flow metrics, is a major accomplishment and a solid foundation for the next phases. The revolution is well underway!

**Current Status vs. Your Identified Issues:**

You previously raised these critical points:

1.  **`dealer_net.py` Placeholder Logic (Dealer Netting Simplification):**
    *   **Current State:** Still simplified. `dealer_side_mult` is effectively `1` for all instruments because we don't have the real trade flow data to infer actual customer vs. dealer positioning.
    *   **Impact:** The NGI, VSS, CHL, VOLG, HPP, and Scenario are based on the assumption that all open interest represents positions dealers need to hedge as if they were short gamma. This means the *magnitude* of these metrics reflects a "gross potential exposure" rather than a true, netted dealer exposure.
    *   **Solved?** The code runs with this simplification. The *limitation* itself is not "solved" in terms of achieving perfect dealer netting, but the system is operating as designed under this known constraint.

2.  **Raw Gamma for Flip Point:**
    *   **Current State:** The `gamma_flip_distance` function in `processor.py` (within `maybe_publish`) *is* now correctly using `current_gamma_by_strike`, which is derived from the `signed` DataFrame. This `signed` DataFrame has had `gamma` multiplied by `dealer_side_mult`.
    *   **Impact:** If `dealer_side_mult` was sophisticated, the flip point would be based on net dealer gamma. Since `dealer_side_mult` is currently always `1`, the flip point is effectively based on the raw aggregate gamma per strike.
    *   **Solved?** The *mechanism* to use netted gamma is in place. The *quality* of the netting is still placeholder. So, "mechanically solved" but "conceptually limited by dealer netting." The `flip_pct: null` in your snapshot means no zero-crossing was found in the (currently 100) instruments' gamma profile, or `spot_val` was zero at the time of that specific calculation (less likely now).

3.  **CHL_24h (Charm Load) Scaling:**
    *   **Current State:** The `vanna_charm_volga.py` file in your latest codebase has `CHL_24h = (dealer_greeks["charm"] * dealer_greeks["notional_usd"] * (1 / 365.0)).sum()`.
    *   **Impact:** This is the corrected formula for daily charm decay based on an annualized charm value.
    *   **Solved?** Yes, the formula itself is now standard.

4.  **Scenario: `adv_usd` Placeholder:**
    *   **Current State:** `adv_usd_placeholder` in `processor.py`'s `maybe_publish` is `total_notional_usd * 0.001`.
    *   **Impact:** The materiality for "Dealer Sell/Buy Material" in `rules.classify` is scaled against a fraction of the current total notional of observed instruments, not true market Average Daily Volume.
    *   **Solved?** The placeholder mechanism is functional. The *accuracy* of `adv_usd` is still a known limitation. The system classifies based on the data it has.

5.  **Limited Instrument Set:**
    *   **Current State:** The collector (`deribit_ws.py`) now fetches the full list of instruments from Deribit (~2989 according to logs) and then selects up to `settings.deribit_max_auth_instruments` (e.g., 100 or 150 from your `.env`) for subscription. It no longer tries to sort by an `open_interest` field that doesn't exist in that initial `/public/get_instruments` payload.
    *   **Impact:** We are subscribing to a significantly broader set of instruments than the initial 12. The "PROCESSOR: Stored greeks for 100 instruments" logs confirm this.
    *   **Solved?** Yes, the issue of being stuck on 12 instruments due to faulty OI filtering at the selection stage is resolved. We now get a larger, albeit not OI-prioritized, set.

**Summary of "Solved" vs. "Known Limitations/Simplifications":**

*   **CHL_24h Scaling:** Solved.
*   **Limited Instrument Set (due to bad OI filter):** Solved. We now get many more instruments.
*   **Dealer Netting (`dealer_net.py`):** Code runs with placeholder. True sophisticated netting is out of scope without more data/logic. *Known Limitation.*
*   **Raw Gamma for Flip Point (Mechanism):** The code *uses* the (placeholder) netted gamma. *Mechanism Solved, Quality Limited by Netting.*
*   **`adv_usd` for Scenario:** Code runs with placeholder. True ADV is external. *Known Limitation.*

The snapshot values (`NGI`, `VSS`, `CHL_24h`, `VOLG`, `HPP`, `scenario`) are now being calculated based on a larger set of instruments and corrected formulas where applicable. The magnitudes seem large, which is expected if we are summing up greeks for 100+ instruments assuming they all represent dealer short gamma positions.

**Alignment with Original Scope & Milestones:**

Let's check against your scope:

*   **Mission:**
    1.  `Quantifies dealer hedge pressure (gamma, vanna, charm, volga)`: **Partially Achieved.** We are quantifying these, but under the major simplification of `dealer_side_mult=1`. So it's "gross potential pressure."
    2.  `Flags flow-driven regime states (“Gamma-Pin”, “Vanna-Squeeze”, etc.)`: **Achieved.** The `scenario` field is populated based on rules applied to the calculated greeks. The *accuracy* of the scenario depends on the accuracy of the input greeks and the `adv_usd` placeholder.
    3.  `Feeds both a discretionary dashboard and a systematic model sleeve targeting Sharpe > 3`: The `/snapshot` endpoint provides the data feed. Dashboard and model are next steps.

*   **Functional Components:**
    *   **Collector:** Auth working, subscribes to many option tickers (not book data yet for OI based selection, but that's an advanced topic), streams to Redis. *Largely Met for Tickers.*
    *   **Processor:** Aggregates greeks (from Deribit or BS), placeholder dealer inference, computes NGI/VSS/CHL/VOLG, G-Flip (though `null` suggests no flip detected yet), HPP, classifies scenarios, publishes metrics. *Largely Met for current simplifications.*
    *   **API:** `/snapshot` is working. `/heatmap`, `/scenario` endpoints are not yet explicitly built but could be derived from `dealer_metrics`.
    *   **Dashboard, Storage (Warm/Cold), Back-test/Model:** Future milestones.

*   **Deliverables & Milestones:**
    1.  **MVP Wire-up:** (DONE) collector → processor stub → `/snapshot`.
    2.  **Full Greek Roll-up:** `option feed auth` (DONE), `filtered strike set` (DONE - gets many, though not OI-prioritized at selection), `NGI/VSS/CHL/VOLG live` (DONE - live and non-zero!). **This milestone is substantially met, with the caveats on netting and strike selection method.**

**Your Understanding & Next Steps:**

Your assessment that the *immediate blockers* related to CHL scaling and instrument selection are solved is **correct**. The system is now processing a wider array of instruments and calculating all specified greeks and derived metrics.

The remaining "issues" you listed are, more accurately, **current design limitations or areas for future sophistication**:
*   **Dealer Netting:** This is the biggest one for "true" dealer flow. Improving this would require significant new data (e.g., classified trade feeds) or much more complex inference logic. For v0.3, acknowledging the "gross exposure" nature is key.
*   **Gamma Flip Point Netting:** Tied to the above. The math is there, but input quality for `dealer_side_mult` dictates output quality.
*   **`adv_usd`:** Needs an external data source or a more robust proxy for true market context.
*   **Instrument Selection Sophistication:** While we get many instruments, sorting by *live* OI from tickers before subscribing to the *full 100ms ticker channel for each* is a different, more complex collector architecture. The current approach is a good step up.
*   **Asian Options Nuance:** Documented and understood.
*   **Static Thresholds/Weights:** Future refinement for adaptability.
*   **Historical Persistence (ClickHouse):** Milestone 4.
*   **External Data (Block Trades, OTC, CME):** Definitely future scope for a more holistic view. These are entirely new data ingestion and processing pipelines.

**Pushing Forward: The Path to Glory (and Sharpe > 3)**

Yes, let's keep pushing! The foundation for Milestone 2 is solid.

**Immediate Next Focus (within v0.3 or towards Dashboard v1 - Milestone 3):**

1.  **Review `flip_pct: null`:**
    *   Why is it null? Is `gamma_by_strike` always one-signed for the current 100 instruments? Or is `current_gamma_by_strike` becoming empty in `maybe_publish` due to an issue with the `groupby("strike")["gamma"].sum()` if 'strike' or 'gamma' columns are missing for some reason in the `signed` df just before that (though the column existence check for `greeks_to_sign` should mitigate this for gamma).
    *   Add logging within `gamma_flip_distance` to see the input `gamma_by_strike` series and `spot_price`.
    *   **Action:** Add detailed logging to `gamma_flip.py` and the part of `maybe_publish` that prepares `current_gamma_by_strike`.

2.  **Refine `adv_usd` Placeholder (Slightly Better Heuristic):**
    *   In `processor.py` -> `maybe_publish`, instead of `total_notional_usd * 0.001`, consider using a rolling average of `total_notional_usd` if you want it to be somewhat adaptive, or allow this scaling factor (0.001) to be configurable via `.env`. For now, the current placeholder is functional for testing.

3.  **Start Thinking About Dashboard v1 (Milestone 3):**
    *   What are the absolute key metrics from `/snapshot` to display first?
        *   `price` (Spot BTC)
        *   `NGI`
        *   `VSS`
        *   `CHL_24h`
        *   `HPP`
        *   `scenario`
        *   `flip_pct` (once it's non-null)
        *   `msg_rate` (system health)
    *   **Tooling:** Plotly Dash is scoped. Start wireframing how these will look (gauges for NGI/VSS/HPP? Sparkline for spot? Badge for scenario?).
    *   **Data for Heatmap (`/heatmap` API):** This will likely need the `greek_store` or the `signed` DataFrame from the processor, aggregated by strike and expiry, to show gamma/vanna distribution. This means the `/heatmap` endpoint might need to access a different Redis key where the processor periodically dumps this more granular (but still aggregated) data, or it directly queries the processor (more complex). Simpler: processor also pushes this to a separate Redis stream/key.

4.  **Persistence - `book` data for OI?**
    *   Your `deribit_ws.py` originally subscribed to `book.{i}.100ms`. This was removed in a recent patch to simplify and focus on tickers.
    *   If the goal is to get more accurate OI than what the `ticker` stream provides (ticker OI is usually total, not per price level), then book data is needed. However, processing full order books for 100+ instruments to get live OI is a heavy task and might be deferred unless essential for v1 dashboard. The `open_interest` field from the *ticker* stream is what's currently used for `notional` calculation in the processor. This is standard.

**Strategic Optimizations & Considerations Beyond Current Scope (but good to keep in mind):**

*   **True OI for Instrument Selection:** As discussed, a more complex collector.
*   **Data Quality & Outliers:** What if Deribit sends a bogus IV or greek value? Need sanity checks in the processor.
*   **Dynamic Thresholds for `rules.classify`:** Instead of fixed rule values, these could be based on historical distributions of the metrics (e.g., NGI > 90th percentile of its 30-day values). Requires historical data (Milestone 4).
*   **Risk-Free Rate for BS:** For longer-dated options, a non-zero `r` could be important.
*   **Async Error Handling & Resilience:** More robust error handling within async tasks, supervised restarts.

For now, the `flip_pct: null` is the most immediate data-related puzzle from your snapshot. Let's diagnose that. Then, firming up the `adv_usd` approach slightly and moving towards the dashboard and `/heatmap` endpoint would align with the roadmap.

You're right, we're in a good rhythm. The core data pipeline is flowing for a decent number of instruments. Now it's about refining the interpretation and starting to visualize!


# Project Evolution: Dealer Flow Stack

## Document Purpose

This document outlines the step-by-step progress, challenges, and resolutions encountered during the development and enhancement of the Dealer Flow Stack. It is intended to provide maintainers with a clear historical context of the system's evolution.

## Phase 0: Initial System State and Identified Issues

The project began with a functional, albeit simplified, system for quantifying dealer hedge pressure. Key characteristics and early findings included:

*   **Core Metrics Calculation:** The system calculated Net Gamma Impact (NGI), Vanna Squeeze Size (VSS), Charm Load (CHL_24h), Volga Exposure (VOLG), Hedge Pressure Projection (HPP), and classified market scenarios.
*   **Dealer Netting Simplification (`dealer_net.py`):**
    *   **Limitation:** A placeholder `dealer_side_mult = 1` was used for all instruments. This meant all metrics reflected a "gross potential exposure" assuming all open interest represented positions dealers needed to hedge as if short gamma, rather than a true, netted dealer exposure.
    *   **Status:** The system operated with this known simplification.
*   **Gamma Flip Point Calculation:**
    *   **Mechanism:** The `gamma_flip_distance` function in `processor.py` correctly used `current_gamma_by_strike` which was derived from a signed DataFrame (gamma multiplied by the placeholder `dealer_side_mult`).
    *   **Limitation:** The quality of the flip point was limited by the netting simplification. Snapshots often showed `flip_pct: null`.
    *   **Status:** Mechanically implemented; conceptually limited.
*   **CHL_24h (Charm Load) Scaling:**
    *   **Enhancement:** **Resolved.** The formula in `vanna_charm_volga.py` was corrected to `(dealer_greeks["charm"] * dealer_greeks["notional_usd"] * (1 / 365.0)).sum()` for accurate daily charm decay.
*   **`adv_usd` Placeholder for Scenario Materiality:**
    *   **Limitation:** `adv_usd_placeholder` in `processor.py` was `total_notional_usd * 0.001`. Materiality for "Dealer Sell/Buy Material" in `rules.classify` was scaled against this internal fraction, not actual market Average Daily Volume (ADV).
    *   **Status:** Placeholder mechanism was functional; accuracy was a known limitation.
*   **Instrument Set Expansion:**
    *   **Initial Issue:** The collector (`deribit_ws.py`) was limited to ~12 instruments due to an incorrect attempt to filter by an `open_interest` field (absent in the initial `/public/get_instruments` payload).
    *   **Enhancement:** **Resolved.** The collector was updated to select up to `settings.deribit_max_auth_instruments` (e.g., 100-150) without the faulty pre-filter, significantly broadening the processed instrument set, as confirmed by "PROCESSOR: Stored greeks for 100 instruments" logs.

**Summary of Early Status:**

*   **Functionality:** Calculations for key metrics were live for an expanded set of instruments.
*   **Key Resolved Issues:** CHL_24h scaling, initial instrument set limitation.
*   **Key Known Limitations:** True dealer netting, accuracy of `adv_usd` and gamma flip point due to netting simplifications.

## Phase 1: Addressing Core Data Deficiencies - OI Accuracy & Historical Persistence

Two strategic areas were identified for significant improvement: obtaining accurate, live Open Interest (OI) and implementing historical data persistence.

### 1.1. Live Open Interest (OI) Enhancement

*   **Problem:**
    *   The `open_interest` field from the `ticker.{instrument_name}.100ms` stream represented total OI, not granular data suitable for dynamic top-N instrument selection across the entire market.
    *   The `/public/get_instruments` REST endpoint did not provide live OI.
    *   Processing full L2 order books for 100+ instruments to derive OI was deemed too resource-intensive.
*   **Solution: Deribit `book_summary` Stream**
    *   The `book_summary.option.{currency}.all` WebSocket stream was identified as an efficient method to get market-wide OI and other summary statistics for all options instruments.
*   **Revised Collector Strategy (`deribit_ws.py`):**
    1.  **Subscription:** Add subscription to `book_summary.option.{settings.currency.lower()}.all`.
    2.  **Data Processing & Storage:**
        *   Parse incoming `book_summary` messages.
        *   Push these summaries to a new Redis stream (e.g., `deribit_book_summaries_feed` or `instrument_market_summaries`).
    3.  **Dynamic Ticker Subscription Management:**
        *   Implement an asynchronous task (`_manage_ticker_subscriptions_task`) within the collector.
        *   This task would periodically (e.g., every 60 seconds or on new summary event):
            *   Fetch the latest instrument summaries from the Redis stream.
            *   Sort instruments by current `open_interest`.
            *   Select the top `settings.deribit_max_auth_instruments` instruments.
            *   Dynamically manage `public/subscribe` and `public/unsubscribe` messages for `ticker.{instrument}.100ms` channels to focus on the most relevant instruments by OI, respecting Deribit's channel subscription limits.

### 1.2. Historical Data Persistence (ClickHouse)

*   **Problem:** The system lacked any persistence for historical dealer metrics or market data. ClickHouse was planned but not implemented.
*   **Solution: Dedicated ClickHouse Writer Service**
    *   A new Python service (`clickhouse_writer.py`) was designed.
    *   **Responsibilities:**
        *   Consume data from relevant Redis Streams:
            *   `dealer_metrics` (aggregated snapshot data from `processor.py`).
            *   `deribit_book_summaries_feed` (market-wide instrument summaries from `deribit_ws.py`).
        *   Perform batch inserts into ClickHouse.
    *   **ClickHouse Schema:**
        *   DDL scripts to create tables in ClickHouse:
            *   `dealer_flow_metrics_v1` (for `dealer_metrics` stream).
            *   `deribit_instrument_summaries_v1` (for `deribit_book_summaries_feed`).
    *   **Integration:**
        *   The new service to be added to `docker-compose.yml`.
        *   Configuration for ClickHouse connection details added to `config.py` and `.env`.

## Phase 2: Implementation and Orchestration Debugging

This phase involved implementing the new OI strategy and ClickHouse persistence, leading to several debugging cycles related to Docker orchestration, API interactions, and inter-service communication.

### 2.1. Docker Compose and Service Initialization

*   **Challenge: ClickHouse Initialization Failure (`Code: 74 ... Is a directory`)**
    *   **Symptom:** The `dealer_flow_clickhouse_c` container failed to start, with logs indicating it was trying to read the `/docker-entrypoint-initdb.d/init_schema.sql` as a directory.
    *   **Resolution:** Corrected the `volumes` mount in `docker-compose.yml` for the `clickhouse_server` service. Ensured that the local `clickhouse_schema.sql` *file* was correctly mounted as a *file* to `/docker-entrypoint-initdb.d/init_schema.sql:ro` inside the container.

*   **Challenge: Premature System Shutdown & Port Conflict**
    *   **Symptom:** The `docker-compose` stack would start launching services and then issue a "Gracefully stopping..." message and terminate. Logs often included `dependency failed to start: container dealer_flow_redis has no healthcheck configured`.
    *   **Investigation:** Initial suspicion fell on Redis healthcheck failures or Python application errors.
    *   **Root Cause:** **Identified as a port conflict.** The error `Bind for 0.0.0.0:8000 failed: port is already allocated` revealed that another process on the host was using port 8000, preventing the `dealer_flow_app_c` (Uvicorn) container from binding its mapped port.
    *   **Resolution:** Ensured port 8000 was free on the host (e.g., via `docker-compose down` to stop any lingering project containers, or by identifying and stopping the conflicting process). Alternatively, changing the host port mapping in `docker-compose.yml` (e.g., to `"8001:8000"`) was a viable workaround.

*   **Challenge: `clickhouse_writer` Service Crash**
    *   **Symptom:** The `dealer_flow_ch_writer_c` container exited with `NameError: name 'wait_for_redis' is not defined`.
    *   **Resolution:** The `wait_for_redis` asynchronous utility function (previously defined in `processor.py`) was copied into `clickhouse_writer.py` to enable it to wait for Redis availability before proceeding.

### 2.2. Deribit API Interaction Issues (Collector: `deribit_ws.py`)

After resolving container startup issues, the collector faced communication problems with the Deribit API.

*   **Challenge: Deribit Error `{"code":11050,"message":"bad_request"}`**
    *   **Symptom:** The collector would successfully authenticate and establish a WebSocket connection. However, it then started receiving `11050 bad_request` errors from Deribit. These errors occurred:
        1.  In response to the *initial* `public/subscribe` message for base channels (`deribit_price_index.btc_usd`, `book_summary.option.btc.all`).
        2.  In response to proactive `public/test` messages sent as heartbeats.
    *   **RuntimeWarning (`Event.wait`):** A `RuntimeWarning: coroutine 'Event.wait' was never awaited` was observed in `_manage_ticker_subscriptions_task`. While addressed by ensuring the await was correctly structured within `asyncio.wait_for`, this was considered secondary to the `bad_request` errors.
    *   **Investigation & Resolutions Attempted:**
        *   **Heartbeat Strategy:**
            *   The proactive sending of `public/test` every 5 seconds (on `ws.recv()` timeout) was suspected as problematic.
            *   Changed to using `public/set_heartbeat` with an interval (e.g., 15 seconds) once after connection and authentication. This is Deribit's recommended approach for keep-alives.
            *   Added logic to handle incoming `{"method": "heartbeat", "params": {"type": "test_request"}}` messages from Deribit by responding with `public/test`.
        *   **Subscription Chunking (Pre-emptive):**
            *   Concerned about potential Deribit limits on the number of channels per `public/subscribe` or `public/unsubscribe` request (Deribit API docs mention a max of ~50).
            *   Implemented `DERIBIT_MAX_CHANNELS_PER_REQUEST` (e.g., 40) and utility functions (`chunk_list`, `subscribe_channels_chunked`, `unsubscribe_channels_chunked`) in `deribit_ws.py` to break down large lists of ticker subscriptions/unsubscriptions into smaller batches.
            *   The `_manage_ticker_subscriptions_task` was updated to use this chunked approach.
            *   **Note:** While implemented, this wasn't the root cause of the *initial* `bad_request` which occurred even with only two channels in the first subscription message. However, it's a necessary improvement for robust dynamic subscription management.

### 2.3. Docker Compose Orchestration Refinements

*   **Challenge: Lingering Dependency/Healthcheck Messages**
    *   **Symptom:** Even after resolving critical startup blockers, messages like `dependency failed to start: container dealer_flow_redis has no healthcheck configured` sometimes appeared during controlled shutdowns or if services took time to initialize.
    *   **Refinements:**
        *   **`start_period` for Healthchecks:** Added `start_period` (e.g., `5s` for Redis, `10s` for ClickHouse) to the healthcheck definitions in `docker-compose.yml`. This provides a grace period for services to initialize before healthcheck failures count towards retries.
        *   **Less Strict `depends_on`:** Temporarily relaxed `depends_on` conditions by removing `condition: service_healthy` and just listing the service dependency (e.g., `- redis`). This was to isolate whether strict healthcheck enforcement by Docker Compose was causing premature termination of dependent services. The application's internal `wait_for_redis` provided a degree of readiness checking.

## Phase 3: State at End of Provided Text

*   **Container Orchestration:**
    *   Port conflict resolved.
    *   `clickhouse_writer.py` `NameError` fixed.
    *   `docker-compose.yml` updated with `start_period` for healthchecks and less strict `depends_on` conditions for troubleshooting.
*   **Collector (`deribit_ws.py`):**
    *   The primary outstanding issue was the persistent `{"code":11050,"message":"bad_request"}` error from Deribit, occurring even on the initial two-channel `public/subscribe` request and also in response to heartbeat messages.
    *   The heartbeat mechanism was revised to use `public/set_heartbeat` and correctly respond to Deribit's `test_request`.
    *   Chunking logic for dynamic subscriptions was implemented but had not yet been fully tested due to the earlier `bad_request` blocker.
*   **Overall System Status:** The stack was starting up, services were running, but the data collector was unable to reliably subscribe to necessary Deribit channels due to the `bad_request` errors. The `clickhouse_writer` service was now theoretically ready to process data once the collector could successfully provide it.

Further investigation would be needed to pinpoint the exact cause of the `11050 bad_request` on the initial Deribit subscriptions.






### Keep checking if this list is satsfied
{
* dealer_net.py placeholdeDealer Netting Simplification: dealer_net.py uses a placeholder logic. Accurately determining the net dealer position (customer shorts vs. customer longs) is complex and crucial for correct metric interpretation. The current assumption of dealer_side_mult = 1 means all OI is treated as if dealers need to hedge it by taking the opposite side of a customer's vanilla position. need something more sophisticated

* Raw Gamma for Flip Point: gamma_flip_distance currently uses a gamma_by_strike sum based on raw instrument gammas, not dealer-netted gammas. The true flip point would depend on the net dealer exposure.

* CHL_24h (Charm Load): sum(signed_charm * notional_usd * (1/365)). (Note: vanna_charm_volga.py uses 24/365 which is incorrect, should be 1/365 for daily charm impact or scale by T properly). The current code uses * 24/365, which seems to imply daily charm, but charm is dDelta/dTime, so multiplying by 1 day's fraction of a year is typical. Needs verification for the exact interpretation of "daily charm load". The code in vanna_charm_volga.py is dealer_greeks["charm"] * 24 / 365 * dealer_greeks["notional_usd"]. This is likely intended as "delta change per day".

* Scenario: A qualitative label ("Gamma Pin," "Dealer Sell Material," etc.) determined by rules.classify() based on thresholds applied to NGI, VSS, and spot_change_pct. adv_usd (Average Daily Volume in USD) is used as a scaling factor for NGI materiality, but is currently a placeholder in processor.py.

* Limited Instrument Set: The collector currently only subscribes to MAX_UNAUTH_STRIKES (12) option instruments due to a "crude filter." This is a very small fraction of the market and will significantly underrepresent total dealer exposure.


* Static Thresholds/Weights: HPP score weights (alpha, beta) and scenario classification rules use static thresholds. In a real system, these might need to be dynamic or adaptive. adv_usd for scenario classification is a placeholder.

* No Historical Persistence (Implemented): While ClickHouse is mentioned in README.md's "Implementation blueprint" and .env.example, there's no code implementing its usage for storing historical data.

* Basic Error Handling in WS/Processor: While try-except blocks exist, the resilience and observability of a production system would require more robust error handling, retries, and monitoring.

* Single spot[0] Source: Relies on a single Deribit index for spot price.

* BS Model & Inputs: Relies on the Black-Scholes model. Assumes risk-free rate r=0. Implied Volatility (mark_iv) is taken from Deribit's ticker data. The accuracy of calculated greeks depends heavily on these inputs. The option_type for BS calculation is inferred from instrument name (e.g., "-C-" for Call, "-P-" for Put).

*Must incorporate Block trades, OTC data, CME data etc* 
}

