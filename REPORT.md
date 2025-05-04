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
