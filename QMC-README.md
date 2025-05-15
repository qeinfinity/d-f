**Project Goal:**

To develop a Python application that calculates the Asian Implied Volatility for every option contract on the Deribit exchange (initially BTC, expandable to ETH) using a Quasi-Monte Carlo (QMC) pricing engine accelerated with Numba. The system must run efficiently on a multi-core CPU (e.g., 16 cores), continuously update the IVs, and provide the results for further use (e.g., display in a web app, data feed).

---

**I. System Architecture & Technologies**

1. **Overall Architecture:**
    - **Master Process:** Orchestrates data fetching, task distribution, and results aggregation.
    - **Worker Processes (Pool):** Leverages `multiprocessing.Pool` to distribute the computationally intensive IV calculation tasks across CPU cores. Each worker operates independently on a subset of option contracts.
2. **Core Technologies & Libraries:**
    - **Python 3.x:** Main programming language.
    - **Numba (`@njit`):** For JIT compilation of the QMC pricing function to achieve C-like speed.
    - **SciPy:**
        - `scipy.stats.qmc.Sobol`: For generating Sobol low-discrepancy sequences.
        - `scipy.stats.norm.ppf`: For inverse normal CDF transformation of Sobol points.
        - `scipy.optimize.brentq`: Robust root-finding algorithm for the IV solver.
    - **NumPy:** For efficient numerical operations, especially if any array operations can be leveraged outside the core Numba loop.
    - **`multiprocessing`:** Python's built-in library for creating and managing worker processes.
    - **`requests` / `websockets` (or a Deribit API client library):** For interacting with the Deribit API to fetch option chain data and market prices. (Consider `deribit_api` Python wrapper if suitable and maintained).
    - **(Optional) `asyncio` / `aiohttp`:** If API interactions need to be non-blocking in the master process while workers compute.

---

**II. Data Structures**

1. **`OptionContract` (Dataclass or named tuple):**
    - `instrument_name: str` (e.g., "BTC-25DEC24-60000-C")
    - `strike_price: float` (K)
    - `expiry_timestamp: float` (Unix timestamp for T_expiry calculation)
    - `option_type: str` ('call' or 'put')
    - `market_price: float` (Current traded price of this option)
    - `underlying_instrument_name: str` (e.g., "BTC-PERPETUAL" or relevant future)
    - `asian_avg_window_details`: (e.g., a dict specifying start offset, duration, sampling interval based on Deribit rules for this contract)
2. **`MarketParameters` (Dataclass or dict):**
    - `underlying_price: float` (S0 - e.g., price of BTC-PERPETUAL or relevant future)
    - `risk_free_rate: float` (r)
3. **`QMCConfig` (Dataclass or dict):**
    - `num_qmc_paths: int`
    - `iv_solver_tolerance: float`
    - `iv_solver_lower_bound: float` (e.g., 0.01)
    - `iv_solver_upper_bound: float` (e.g., 5.00)
4. **`CalculationResult` (Dataclass or named tuple):**
    - `instrument_name: str`
    - `asian_implied_volatility: float` (or None if failed)
    - `model_price_at_iv: float` (QMC price using the solved IV)
    - `error_code: int` (0 for success, other for specific errors)
    - `calculation_time_ms: float`

---

**III. Key Modules & Functions**

1. **`deribit_connector.py` (Deribit API Interaction)**
    - `fetch_active_option_chain(asset='BTC') -> list[OptionContract]`
        - Gets all active option instruments.
        - Parses instrument names to extract K, T, type.
        - Determines Asian averaging window details based on Deribit rules (5min vs 30min, sampling freq).
    - `fetch_market_data(instrument_names: list[str], underlying_name: str) -> (dict[str, float], float)`
        - Gets ticker data (best bid/ask or last price) for specified option instruments.
        - Gets price for the underlying.
        - Returns a dict of `instrument_name: market_price` and `underlying_price`.
2. **`qmc_tools.py` (QMC Sequence Generation)**
    - `get_qmc_sobol_generator(dimensions: int, scramble: bool = False, seed: Optional[int] = None) -> Sobol`
        - Initializes and returns a `scipy.stats.qmc.Sobol` generator.
        - `dimensions` will be max number of random draws needed per QMC path.
3. **`asian_pricer_numba.py` (Core QMC Asian Option Pricer)**
    - `@njit(fastmath=True, nogil=True)qmc_asian_option_price(S0, K, T_expiry, r, sigma_trial, option_type_int, avg_window_start_offset, avg_window_duration, num_avg_samples, num_qmc_paths, sobol_points_2d_array) -> float`:
        - `option_type_int`: 0 for call, 1 for put (Numba likes simple types).
        - `sobol_points_2d_array`: A NumPy array of shape `(num_qmc_paths, dimensions_per_path)` containing pre-generated Sobol points [0,1).
        - **Algorithm:**
            1. Initialize `cumulative_payoff = 0.0`.
            2. Calculate `dt_avg_sample = avg_window_duration / num_avg_samples`.
            3. Loop `i` from 0 to `num_qmc_paths - 1`:
                - `current_S = S0`.
                - `path_avg_sum = 0.0`.
                - `qmc_variate_idx = 0`.
                - **(A) Simulate to start of averaging window (if `avg_window_start_offset > 0`):**
                    - `Z = norm_ppf_numba(sobol_points_2d_array[i, qmc_variate_idx])`
                    - `current_S = current_S * exp((r - 0.5 * sigma_trial^2) * avg_window_start_offset + sigma_trial * sqrt(avg_window_start_offset) * Z)`
                    - `qmc_variate_idx += 1`.
                    - *(Antithetic: Store `Z_anti = -Z` for antithetic path)*
                - **(B) Simulate through averaging window:**
                    - Loop `j` from 0 to `num_avg_samples - 1`:
                        - `Z = norm_ppf_numba(sobol_points_2d_array[i, qmc_variate_idx])`
                        - `current_S = current_S * exp((r - 0.5 * sigma_trial^2) * dt_avg_sample + sigma_trial * sqrt(dt_avg_sample) * Z)`
                        - `path_avg_sum += current_S`.
                        - `qmc_variate_idx += 1`.
                        - *(Antithetic: Update `current_S_anti` using `Z` and sum to `path_avg_sum_anti`)*
                - `avg_price = path_avg_sum / num_avg_samples`.
                - Calculate payoff for `avg_price`. Add to `cumulative_payoff`.
                - *(Antithetic: Calculate payoff for `avg_price_anti`. Add to `cumulative_payoff`)*
            4. `num_effective_paths = num_qmc_paths` (or `num_qmc_paths * 2` if antithetic).
            5. `mean_raw_payoff = cumulative_payoff / num_effective_paths`.
            6. Return `mean_raw_payoff * exp(-r * T_expiry)`.
    - `@njit(fastmath=True, nogil=True)norm_ppf_numba(u: float) -> float`: (A Numba-compatible inverse normal CDF. SciPy's is not directly usable in `@njit` mode. You might need to implement a simple approximation like Acklam's or use a Numba-compatible library if one exists, or pass transformed normal variates directly to the pricer). *This is a key detail to solve for Numba compatibility.*
        - *Alternative for `norm_ppf_numba`: Pre-transform Sobol points to normal variates using `scipy.stats.norm.ppf` in the main Python code and pass the array of normal variates to the Numba function.* This is often the cleaner solution.
4. **`iv_solver.py` (Implied Volatility Calculation)**
    - `calculate_asian_iv(contract: OptionContract, market_params: MarketParameters, qmc_config: QMCConfig, sobol_generator: Sobol) -> CalculationResult`:
        1. Define objective function `objective_func(sigma_trial)`:
            - Generate/fetch required `sobol_points_2d_array` for `sigma_trial` using `sobol_generator.random(qmc_config.num_qmc_paths)`.
            - *(Transform to normal variates if `norm_ppf_numba` is not used inside pricer).*
            - Call `qmc_asian_option_price(...)` with `sigma_trial`.
            - Return `(model_price - contract.market_price)`.
        2. Try:
            - `asian_iv = scipy.optimize.brentq(objective_func, qmc_config.iv_solver_lower_bound, qmc_config.iv_solver_upper_bound, xtol=qmc_config.iv_solver_tolerance)`
            - Recalculate model price at `asian_iv` for reporting.
            - Return `CalculationResult` (success).
        3. Except (e.g., `ValueError` if `brentq` fails, or if `objective_func` values at bounds have same sign):
            - Return `CalculationResult` (error).
5. **`main_orchestrator.py` (Main Application Logic & Parallel Processing)**
    - Global `QMCConfig` instance.
    - `worker_calculate_iv(task_args) -> CalculationResult`:
        - Unpacks `task_args` (contract, market_params, qmc_config).
        - Initializes a `Sobol` generator (ensure workers have different states if not re-initialized per call, e.g., by advancing the sequence or using different seeds if scrambled). Scipy's Sobol, when `draw` or `random` is called, advances its state.
        - Calls `calculate_asian_iv()`.
        - Returns `CalculationResult`.
    - `run_update_cycle()`:
        1. `active_contracts = deribit_connector.fetch_active_option_chain()`.
        2. `(option_market_prices, underlying_s0) = deribit_connector.fetch_market_data(...)`.
        3. Update `market_price` in `active_contracts`.
        4. `market_params = MarketParameters(underlying_price=underlying_s0, risk_free_rate=...)`.
        5. Prepare `tasks = [(contract, market_params, QMC_CONFIG) for contract in active_contracts if contract.market_price is not None]`.
        6. `with multiprocessing.Pool(processes=16) as pool:`
            - `results = pool.map(worker_calculate_iv, tasks)`
        7. Process `results`: log, store, send to UI, etc.
    - Main loop: `while True: run_update_cycle(); time.sleep(UPDATE_INTERVAL_SECONDS)`.

---

**IV. Detailed Algorithm Flow (Single Update Cycle):**

1. **Master:** Initiates `run_update_cycle()`.
2. **Master:** Calls `deribit_connector` to fetch:
    - Full list of active option instruments (metadata like K, T, type, Asian window rules).
    - Current market prices for all these options.
    - Current price of the underlying BTC asset.
3. **Master:** Prepares a list of `task_args`. Each item contains all necessary data for one option contract to have its Asian IV calculated (its `OptionContract` object, the global `MarketParameters`, and the `QMCConfig`).
4. **Master:** Submits this list of `task_args` to the `multiprocessing.Pool`'s `map` function, which distributes one `task_args` to each call of `worker_calculate_iv` across the 16 worker processes.
5. **Each Worker Process (executing `worker_calculate_iv`):**a. Receives its `task_args`.b. Initializes or gets access to a Sobol QMC sequence generator. *Crucially, if workers are long-lived and reuse generators, ensure they operate on different parts of the sequence or are re-seeded appropriately if scrambling is used. For `pool.map`, usually, each task is a fresh call, so initializing Sobol inside `worker_calculate_iv` is fine.*c. Calls `calculate_asian_iv` with the contract data.d. **Inside `calculate_asian_iv`:**i. The `brentq` root-finder is invoked.ii. `brentq` repeatedly calls the `objective_func`.iii. **Inside `objective_func` (for each `brentq` iteration):**1. A new batch of `num_qmc_paths` Sobol points is drawn.2. *(These points are transformed to standard normal deviates if this isn't done inside the Numba pricer).*3. The Numba-jitted `qmc_asian_option_price` function is called with the current `sigma_trial` from `brentq` and the Sobol normal deviates.4. The Numba function executes all QMC paths (simulating asset price evolution, averaging, calculating payoff, applying antithetics) at high speed.5. The model price is returned to `objective_func`.6. `objective_func` returns `(model_price - market_price)` to `brentq`.iv. `brentq` converges to the `asian_iv`.e. The worker returns the `CalculationResult` (containing the solved `asian_iv`) back to the master.
6. **Master:** Collects all `CalculationResult` objects from `pool.map`.
7. **Master:** Processes these results (e.g., logs to console/file, stores in a database, sends to a front-end via WebSocket).
8. **Master:** Pauses for the configured `UPDATE_INTERVAL_SECONDS` and then repeats the cycle.

---

**V. Optimization & Performance Considerations:**

- **Numba `norm_ppf`:** Solve this. Passing pre-transformed normal variates (NumPy array from `scipy.stats.norm.ppf(sobol_generator.random(...))`) into the Numba pricer is the most straightforward and performant way. The Numba pricer then just consumes these normal variates.
- **Antithetic Variates:** Ensure implementation within the Numba pricer as it nearly halves computation for the same variance reduction.
- **QMC Paths:** Experiment to find the minimum `num_qmc_paths` for stable IVs. Too few can make the `objective_func` noisy, hindering `brentq`.
- **Minimize Data Transfer:** Pass only essential data to worker processes. Python's `multiprocessing` involves pickling/unpickling, which can have overhead for very large objects. Our `OptionContract` and `MarketParameters` are small.
- **Sobol Generator Scrambling:** Scrambling can improve QMC properties but adds a small overhead. Test if it's beneficial for your IV stability.
- **Smart Task Distribution:** `pool.map` handles chunking. If some options consistently take much longer (e.g., very long-dated), this could lead to load imbalance, but for a typical chain, it should be fairly even.

---

**VI. Testing Strategy:**

1. **Pricer Unit Tests:**
    - Test `qmc_asian_option_price` against known values for simple cases (e.g., compare with a simpler geometric Asian option which has a closed form, or against a well-validated MC from another source).
    - Test edge cases (deep ITM/OTM, near expiry).
2. **IV Solver Unit Tests:**
    - Generate a known Asian option price with a known volatility using your pricer. Feed this price to `calculate_asian_iv` and ensure it recovers the original volatility.
3. **Integration Tests:**
    - Test the full pipeline with a small, fixed set of mock option contracts.
    - Verify parallel processing and results aggregation.
4. **Performance Profiling:**
    - Use `cProfile` or `line_profiler` (with Numba, profiling can be tricky, focus on the Python parts and infer Numba performance) to identify bottlenecks outside the Numba code.
    - Measure end-to-end update cycle time.

----

lets consider another direction. were in the process of building this dealer flow stack. my main interest in asian deribit pricing is to be able to use asian pricing in the dealer flow stack if we find that we need to. it might make sense to build it directly in here given the data ingestion foundations are already in place but mostly because we actually need to have the option to use asian pricing in the dealer flow stack if testing shows that using it helps more accurately describes the flows we're trying to ascertain. this will then become more complex when we go on to incorporate CME data and combining all of those flows correctly 

----
Okay, this is a fascinating and highly relevant pivot! Integrating Asian option pricing directly into your "Dealer-Flow Stack" is a sophisticated step, especially if you suspect that the European Black-Scholes (BS) model (currently in your `greek_calc.py`) isn't fully capturing the nuances of Deribit's Asian-settled options, particularly for dealer hedging flows.

The goal is to have the *option* to use an Asian pricing model to derive greeks within your existing infrastructure, especially if it proves more descriptive. This will indeed become more complex with CME data (which are standard European options), so building a modular and configurable greek calculation engine is wise.

Here's an implementation blueprint for integrating Asian QMC pricing into your `dealer-flow-stack`:

**Core Idea:**

Modify `processor.py` so that when it needs to calculate greeks itself (i.e., Deribit doesn't provide them in the ticker, or you explicitly want to override), it can choose between the existing European `bs_greeks` and a new Asian QMC-based greek calculator. The input volatility for the Asian QMC model will still primarily be derived from Deribit's `mark_iv` (which is itself a European BS implied volatility).

**I. New Module: `asian_qmc_pricer.py`**

This module will house the Numba-jitted QMC engine for pricing Asian options and calculating their greeks.

1. **`qmc_asian_option_price_core` (Numba JIT Function):**
    - **Purpose:** Calculates the price of an arithmetic Asian option using QMC. This is the high-performance core.
    - **Inputs:** `S` (current underlying price), `K` (strike), `T` (time to expiry, years), `r` (risk-free rate), `sigma` (volatility), `option_type_int` (e.g., 1 for Call, 0 for Put), `avg_params` (a Numba-compatible structure/tuple holding averaging window start offset from now, duration, number of samples), `sobol_normal_variates_2d_array` (pre-generated Sobol points already transformed to standard normal deviates, shape: `(num_paths, num_dimensions_per_path)`).
    - **Logic:**
        - Simulate price paths to the start of the averaging window.
        - Simulate prices through the averaging window using `dt_avg_sample`.
        - Calculate arithmetic average for each path.
        - Calculate payoff for each path.
        - Apply antithetic variates (use `Z` for each `Z` normal variate to get two paths per Sobol point).
        - Average discounted payoffs.
    - **Output:** Asian option price (float).
    - **Annotation:** `@njit(fastmath=True, nogil=True)`
2. **`calculate_asian_greeks_qmc` (Python Function, orchestrates Numba calls):**
    - **Purpose:** Calculates selected Asian greeks (initially Gamma, potentially Delta) using finite differences with the `qmc_asian_option_price_core`.
    - **Inputs:**
        - `S0`, `K`, `T`, `r`, `input_sigma` (from `mark_iv`).
        - `option_type_str` ("C" or "P").
        - `avg_window_details` (dict: `start_offset_from_now`, `duration`, `num_avg_samples`).
        - `qmc_config` (dict: `num_paths`, `bump_factor_price`, `bump_factor_vol`, `sobol_generator` instance from `scipy.stats.qmc.Sobol`).
        - `(Optional)` `greeks_to_calc: list[str]` (e.g., `["gamma", "delta"]`).
    - **Logic:**
        - **Prepare Parameters:** Convert inputs into the format needed by `qmc_asian_option_price_core` (e.g., `option_type_int`, `avg_params` tuple).
        - **Sobol Variates:** For each price calculation needed for finite differences, draw a fresh batch of Sobol points from `qmc_config.sobol_generator` and transform them to normal variates using `scipy.stats.norm.ppf`. *Crucially, for calculating a single greek like Gamma (P_up, P_down, P0), you might want to use the same set of Sobol numbers for all three price evaluations by applying the S-bump to the path generation, to reduce variance of the greek estimate. This is more complex. Simpler first pass: independent Sobol draws for each price point.*
        - **Calculate Base Price (P0):** Call `qmc_asian_option_price_core` with base parameters.
        - **Calculate Asian Delta (if requested):**
            - `dS = S0 * qmc_config.bump_factor_price`.
            - `P_up_S = qmc_asian_option_price_core(S0 + dS, ...)`
            - `P_down_S = qmc_asian_option_price_core(S0 - dS, ...)`
            - `asian_delta = (P_up_S - P_down_S) / (2 * dS)`.
        - **Calculate Asian Gamma (if requested):**
            - Needs P0, P_up_S, P_down_S (already calculated if Delta was).
            - `asian_gamma = (P_up_S - 2 * P0 + P_down_S) / (dS ** 2)`.
        - **Asian Vanna, Charm, Volga (Future/Stubbed):** These are more complex to calculate efficiently via QMC bumping (many more QMC calls). Initially, these can return `0.0` or `None`, or we can decide to calculate them later if performance allows.
            - *Vanna (dDelta/dSigma or dVega/dS)*: Would require bumping `input_sigma` and recalculating Asian Delta, or calculating Asian Vega and then bumping `S`.
    - **Output:** A dictionary like `{"gamma": asian_gamma, "delta": asian_delta, "vanna": 0.0, ...}`.
    - **Performance:** This function will be called per option if Asian greeks are chosen. Each greek calculation via bumping means multiple full QMC pricing runs.

**II. Modifications to `dealer_flow/config.py` (`Settings` class)**

```
pythonCopy code
class Settings(BaseSettings):
    # ... existing settings ...
    use_asian_greeks_fallback: bool = False  # Master switch: True to enable Asian QMC as fallback
    asian_greeks_expiry_threshold_days: float = 7.0 # Use Asian greeks if T <= this value (days)
    # Set to 0 or negative if Asian should always be used when use_asian_greeks_fallback=True and Deribit greeks missing

    qmc_asian_num_paths: int = 10000          # Number of paths for Asian QMC
    qmc_asian_price_bump_factor: float = 0.01 # For S bump in Delta/Gamma: dS = S * factor
    # qmc_asian_vol_bump_factor: float = 0.005  # For sigma bump if calculating Vanna/Volga: dSigma = sigma * factor (or absolute)

    # Ensure deribit_max_auth_instruments is present if used by collector
    deribit_max_auth_instruments: int = 100 # Example

    # Add dynamic subscription refresh interval if used in revised collector
    dynamic_subscription_refresh_interval_seconds: int = 600 # Example: 10 minutes

    class Config:
        env_file = Path(__file__).parent.parent / ".env"

settings = Settings()

```

**III. Modifications to `dealer_flow/processor.py`**

1. **Imports:**
    
    ```
    pythonCopy code
    from dealer_flow.asian_qmc_pricer import calculate_asian_greeks_qmc # If separate file
    # from .asian_qmc_pricer import ... # if in same dir
    from dealer_flow.config import settings
    from scipy.stats import qmc # For Sobol generator instance
    
    ```
    
2. **Global QMC Sobol Generator (Initialize once):**
    
    ```
    pythonCopy code
    # At the top of processor.py, after imports
    # Determine max dimensions needed by QMC pricer (e.g., steps to avg_start + num_avg_samples)
    # This is a placeholder, needs to be calculated based on option with longest averaging needs
    MAX_QMC_DIMENSIONS = 350 # Example: 1 jump + 300 avg samples for 30-min / 6s sampling + buffer
    sobol_generator_global = qmc.Sobol(d=MAX_QMC_DIMENSIONS, scramble=False) # Scramble True can be better
    # You might need to skip initial points if running multiple processors or ensure state isn't shared badly
    # For multiprocessing (if processor.py is run in parallel, which it isn't with current start.sh), each process needs its own.
    # For asyncio, this global instance is fine.
    
    ```
    
3. **Inside the `processor` async while loop, within the ticker processing block:**
    
    ```
    pythonCopy code
    # ... after fetching inst, strike, T, mark_price, open_interest, current_underlying_price ...
    # ... and after deriv_greeks = msg_payload.get("greeks", {}) ...
    
    gamma = None # Initialize to None
    vanna = None
    charm = None
    volga = None
    delta = None # If you decide to calculate/store it
    calculated_greeks_source = "deribit" # Default assumption
    
    # Try to get greeks from Deribit first
    gamma_deribit = deriv_greeks.get("gamma")
    vanna_deribit = deriv_greeks.get("vanna")
    charm_deribit = deriv_greeks.get("charm")
    volga_deribit = deriv_greeks.get("volga")
    # delta_deribit = deriv_greeks.get("delta")
    
    if gamma_deribit is not None: # Assuming if gamma is present, others might be too (or we take what we get)
        gamma = float(gamma_deribit)
        vanna = float(vanna_deribit) if vanna_deribit is not None else 0.0
        charm = float(charm_deribit) if charm_deribit is not None else 0.0
        volga = float(volga_deribit) if volga_deribit is not None else 0.0
        # delta = float(delta_deribit) if delta_deribit is not None else 0.0
    else:
        # Deribit didn't provide greeks, we need to calculate them.
        # Decide whether to use Asian QMC or European BS based on config and conditions
        time_to_expiry_days = T * 365.0
        should_use_asian = (
            settings.use_asian_greeks_fallback and
            (settings.asian_greeks_expiry_threshold_days <= 0 or
             time_to_expiry_days <= settings.asian_greeks_expiry_threshold_days)
        )
    
        sigma_input_for_calc = msg_payload.get("mark_iv", 0.0) / 100.0 # From Deribit ticker
        option_type_char = "C" if "-C-" in inst else ("P" if "-P-" in inst else None)
    
        if option_type_char and sigma_input_for_calc > 0 and T > 0 and current_underlying_price > 0:
            if should_use_asian:
                calculated_greeks_source = "asian_qmc"
                logger.debug(f"PROCESSOR: Using Asian QMC for {inst} (T={T*365:.1f}d)")
    
                # Simplified avg_window_details - needs actual Deribit logic for 5m/30m window
                # This is a placeholder, real logic needed based on expiry alignment
                # For Deribit: average over last 30 or 5 minutes before expiry.
                # If T is current time to expiry, avg_window_start_offset = T - (30_mins_in_years)
                # avg_duration = 30_mins_in_years. num_samples based on 6s interval.
                # This needs careful implementation:
                avg_duration_seconds = 30 * 60 if "W" in inst or "M" in inst or "Q" in inst else 5*60 # Approximation
                avg_duration_years = avg_duration_seconds / (365 * 24 * 3600)
                num_avg_samples_calc = int(avg_duration_seconds / 6) # 6-second sampling
    
                # This needs to be calculated correctly based on T (time to true expiry)
                # vs. when the averaging window starts. For simplicity, assume we are before averaging.
                avg_start_offset_from_now_years = max(0, T - avg_duration_years) # If T < avg_duration, we are in it.
                # A full implementation would also handle being *inside* the averaging window.
    
                asian_avg_params_for_pricer = { # Structure this for Numba if qmc_asian_option_price_core needs tuple/array
                    "start_offset_from_now": avg_start_offset_from_now_years,
                    "duration": avg_duration_years, # The actual averaging period's duration
                    "num_samples": num_avg_samples_calc
                }
    
                qmc_runtime_config = {
                    "num_paths": settings.qmc_asian_num_paths,
                    "bump_factor_price": settings.qmc_asian_price_bump_factor,
                    "sobol_generator": sobol_generator_global # Pass the global instance
                }
    
                try:
                    # Note: calculate_asian_greeks_qmc needs to be async if it contains async calls,
                    # or run in executor if it's CPU-bound sync code (which it is).
                    # For now, assuming it's a sync function. If too slow, needs to run in executor.
                    asian_greeks_dict = await asyncio.get_event_loop().run_in_executor(
                        None, # Uses default ThreadPoolExecutor
                        calculate_asian_greeks_qmc, # The sync function
                        current_underlying_price, K_param_bs.item(), T, 0.0, # r=0
                        sigma_input_for_calc, option_type_char,
                        asian_avg_params_for_pricer, # Pass the structured params
                        qmc_runtime_config
                    )
                    gamma = asian_greeks_dict.get("gamma", 0.0)
                    vanna = asian_greeks_dict.get("vanna", 0.0) # If calculated
                    charm = asian_greeks_dict.get("charm", 0.0) # If calculated
                    volga = asian_greeks_dict.get("volga", 0.0) # If calculated
                    # delta = asian_greeks_dict.get("delta", 0.0)
                except Exception as e_ag:
                    logger.error(f"PROCESSOR: Asian QMC failed for {inst}: {e_ag}", exc_info=True)
                    # Fallback to 0.0 if QMC errors out
                    gamma, vanna, charm, volga = 0.0, 0.0, 0.0, 0.0
                    calculated_greeks_source = "asian_qmc_error"
    
            else: # Use European BS
                calculated_greeks_source = "european_bs"
                S_param_bs = np.array([current_underlying_price])
                K_param_bs = np.array([strike]) # strike is already float
                option_type_bs_int = 1 if option_type_char == "C" else 0
    
                _g_bs, _v_bs, _c_bs, _vg_bs = bs_greeks(
                    S_param_bs, K_param_bs, np.array([T]),
                    0.0, # r
                    np.array([sigma_input_for_calc]),
                    np.array([option_type_bs_int])
                )
                gamma = float(_g_bs[0]) if not np.isnan(_g_bs[0]) else 0.0
                vanna = float(_v_bs[0]) if not np.isnan(_v_bs[0]) else 0.0
                charm = float(_c_bs[0]) if not np.isnan(_c_bs[0]) else 0.0
                volga = float(_vg_bs[0]) if not np.isnan(_vg_bs[0]) else 0.0
        else: # Conditions for calculation not met (bad sigma, T, price, or option_type)
            calculated_greeks_source = "calc_skipped_bad_inputs"
            gamma, vanna, charm, volga = 0.0, 0.0, 0.0, 0.0
    
    # Ensure greeks are float, default to 0.0 if None after all logic
    gamma = gamma if gamma is not None else 0.0
    vanna = vanna if vanna is not None else 0.0
    charm = charm if charm is not None else 0.0
    volga = volga if volga is not None else 0.0
    # delta = delta if delta is not None else 0.0
    
    # Store in greek_store
    final_greeks_payload = {
        "gamma": gamma, "vanna": vanna, "charm": charm, "volga": volga,
        # "delta": delta,
        "notional_usd": notional, # Calculated earlier
        "strike": strike, # Already float
        "source": calculated_greeks_source, # Add source for debugging/analysis
        "T": T, # Store T for verification
        "mark_iv_used": sigma_input_for_calc if calculated_greeks_source != "deribit" else msg_payload.get("mark_iv", 0.0),
        "S_used": current_underlying_price if calculated_greeks_source != "deribit" else None
    }
    greek_store[inst] = final_greeks_payload
    # ... rest of your ticker processing and maybe_publish logic ...
    
    ```
    

**IV. Key Logic for Asian Averaging Window in `processor.py` (Needs Deribit Specifics):**

Deribit's daily/weekly/monthly options settle against a TWAP of the index in the last 30 minutes (or sometimes 1 hour for longer expiries, check docs) before the 08:00 UTC expiry. Futures-tied options use a 5-minute window aligned with future expiry.

- You need a function `get_asian_window_details(instrument_name: str, expiry_timestamp_utc: float, current_timestamp_utc: float) -> dict`:
    - This function will parse the instrument name to determine if it's a daily, weekly, monthly, quarterly, or futures-aligned option.
    - Based on type, it determines the averaging window duration (e.g., 30 mins = `30*60` seconds) and sampling interval (e.g., 6 seconds).
    - `num_avg_samples = duration_seconds / sampling_interval_seconds`.
    - `avg_window_true_end_time_utc = expiry_timestamp_utc`.
    - `avg_window_true_start_time_utc = avg_window_true_end_time_utc - duration_seconds`.
    - `avg_window_start_offset_from_now_seconds = max(0, avg_window_true_start_time_utc - current_timestamp_utc)`.
    - `avg_window_start_offset_from_now_years = avg_window_start_offset_from_now_seconds / (365*24*3600)`.
    - `avg_duration_years = duration_seconds / (365*24*3600)`.
    - **Handling "In-Average" state:** If `current_timestamp_utc > avg_window_true_start_time_utc`, the option is *in* its averaging period. The QMC pricer would need historical fixings up to `current_timestamp_utc` and would only simulate the remainder of the averaging period. This blueprint currently assumes pricing *before* the averaging period starts for simplicity (common use case for greeks far from expiry). Adapting `qmc_asian_option_price_core` for in-average pricing adds complexity.

**V. Performance Considerations:**

- Running `calculate_asian_greeks_qmc` (which involves multiple QMC pricing calls) for many instruments in the `processor.py`'s async loop, even with `run_in_executor`, will be CPU intensive. Your 16-core machine will be put to work.
- The number of paths (`qmc_asian_num_paths`) and the efficiency of the Numba code are critical.
- You might need to make the `asian_greeks_expiry_threshold_days` quite small initially (e.g., 1-2 days) or only enable it for a subset of instruments to manage load.

**VI. Testing:**

- Unit test `qmc_asian_option_price_core` against known benchmarks or approximations if possible.
- Test `calculate_asian_greeks_qmc` for a single option and check if greeks are "sensible" (e.g., Asian gamma often lower than European for ATM options).
- Performance test the processor with Asian greeks enabled for a realistic number of instruments.

This blueprint provides a pathway to integrate configurable Asian QMC-based greeks into your dealer flow stack. The main challenge will be balancing accuracy (more paths, more greeks calculated) with performance. Starting with just Asian Gamma as an alternative to BS Gamma could be a good first step.