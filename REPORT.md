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

