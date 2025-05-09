https://tr8dr.github.io/AsianOptions/

You've hit on a **very important and complex point** regarding Deribit options, and it has significant implications for how the "Dealer-Flow Stack" should be built and interpreted.

Let's break down the implications of Deribit's BTC options being **Asian options settled against an average price**, versus the common assumption/practice of pricing and quoting greeks as if they were European options.

**Understanding Asian vs. European Options:**

*   **European Option:** Payoff depends on the price of the underlying asset at a single point in time: the exact moment of expiry. The Black-Scholes model (used in `greek_calc.py`) is designed for European options.
*   **Asian Option (Average Price Option):** Payoff depends on the average price of the underlying asset over a specified period *leading up to expiry*. Deribit's BTC options (daily, weekly, monthly, quarterly) typically settle against a TWAP (Time-Weighted Average Price) of the relevant index (e.g., Deribit BTC index) over the **last 30 minutes or 1 hour before expiry**.

**Your Caveats and Observations are Key:**

1.  **Market Participants Pricing as European:** It's highly plausible that many, if not most, participants (including some dealers) use European option models (like Black-Scholes) for pricing, risk management, and greek calculations for Deribit options. This is due to:
    *   **Simplicity and Ubiquity:** European models are well-understood, widely implemented, and computationally less intensive.
    *   **Liquidity and Quoting Conventions:** If the market predominantly quotes and trades based on European model outputs (e.g., implied volatilities derived from Black-Scholes), participants need to align with these conventions to effectively trade.
    *   **Complexity of Asian Models:** Accurate pricing and greek calculation for Asian options are significantly more complex. Closed-form solutions like Turnbull-Wakeman exist for geometric Asian options, but arithmetic Asian options (which Deribit's are, based on an arithmetic average) often require Monte Carlo simulations or complex approximations (e.g., Levy, Curran-Conlon).
2.  **Deribit's Quoted Greeks Potentially European:** This is also very likely. Exchanges often provide greeks based on standard, widely accepted models for ease of use and comparability, even if the underlying settlement has nuances. Providing true Asian option greeks would be a significant undertaking and might confuse participants accustomed to European greeks.

**Impact on the "Dealer-Flow Stack" and How it Should Be Built/Interpreted:**

1.  **`greek_calc.py` (Black-Scholes Engine):**
    *   **Current State:** Uses Black-Scholes, which is for European options.
    *   **Implication:** If dealers are *actually* hedging based on the true Asian nature of the option (especially as expiry approaches), then the greeks calculated by `greek_calc.py` will be **approximations** and may **diverge significantly from the true Asian option greeks**, particularly for:
        *   **Gamma and Vanna near expiry:** The path-dependent nature of Asian options means their gamma profile "smooths out" near expiry compared to European options, which have a sharp gamma peak at the strike. Vega also behaves differently.
        *   **Delta:** The delta of an Asian option can be less sensitive to spot price movements far from the averaging period, and more sensitive to movements *within* the averaging period.
    *   **What to do:**
        *   **Acknowledge the Approximation:** The system should clearly document that its BS-calculated greeks are European approximations of what are technically Asian options.
        *   **Validate Against Deribit's Greeks:** If Deribit provides greeks via its ticker feed (`d.get("greeks", {})`), the `processor.py` currently uses them if available. This is a good pragmatic approach *if Deribit's greeks are also based on a European model*. If Deribit's greeks *were* true Asian greeks, then your `bs_greeks` would be a fallback to a different model type.
        *   **Consider an "Asian Adjustment" Model (Advanced):** For a more sophisticated system, one might consider implementing an adjustment layer or a simplified Asian option model, especially for options nearing their averaging period. This is non-trivial. For example, one could try to estimate the "effective strike" and "effective volatility" for an Asian option and plug those into a BS model as an approximation.
        *   **Focus on Shorter Averaging Windows:** The impact is most pronounced for options *very close* to or *within* their final averaging window (e.g., last 30-60 mins for Deribit). For options further from expiry, the European approximation might be more reasonable.

2.  **Dealer Hedging Behavior:**
    *   **The Core Question:** Are dealers hedging based on European greeks (because it's simpler, or that's what their systems use, or they believe the market trades on them) or are they adjusting their hedges for the Asian settlement, especially near expiry?
    *   **Likely Scenario:**
        *   **Far from Expiry:** Dealers probably use European greeks as a primary guide.
        *   **Approaching/During Averaging Period:** Sophisticated dealers will *definitely* account for the Asian settlement. Their hedging will aim to match the *average price exposure*, not just the spot price at expiry. This could mean:
            *   Less aggressive gamma hedging of spot movements outside the averaging window if they believe the average won't be significantly impacted.
            *   More active trading during the averaging period itself to sculpt their exposure to the evolving average.
    *   **Implication for Your System:** If your system calculates European greeks, the "dealer flow" it predicts might not perfectly match the actual hedging activities of dealers who are Asian-aware, especially near settlement. The NGI, VSS, etc., would represent the flow *if* options were European.

3.  **`processor.py` - Using Deribit's Greeks vs. `bs_greeks`:**
    *   Your current logic prefers Deribit's greeks if available:
        ```python
        deriv_greeks = d.get("greeks", {})
        gamma = deriv_greeks.get("gamma", 0.0)
        vanna  = deriv_greeks.get("vanna") # etc.
        if None in (vanna, charm, volga): # or other higher-order greeks
            # ... call bs_greeks ...
        ```
    *   **This is a sensible default if you assume Deribit's quoted greeks are also European approximations.** It means your system aligns with the greeks the exchange itself publishes.
    *   **If Deribit's greeks WERE true Asian greeks (unlikely for the common ones),** then your `bs_greeks` fallback would be a switch to a different model, which might be less accurate for the actual instrument.
    *   **Consistency is Key:** It's probably best to aim for consistency. If the market primarily thinks in European terms for these, then using European-derived greeks (either from Deribit or your BS model) makes the output interpretable in that context.

4.  **Interpretation of Metrics (NGI, VSS, HPP, Gamma Flip):**
    *   All these metrics will be based on the greeks used (European from Deribit or European from your `bs_greeks`).
    *   **Gamma Flip:** The concept of a sharp gamma flip point is more characteristic of European options. For Asian options, the transition might be smoother. The calculated flip point would be the "European-equivalent" flip.
    *   **Hedging Flows:** The system will predict hedging flows *as if* options were European. This is likely a good first-order approximation for much of the option's life but will be less accurate for the very end-of-life dynamics.

5.  **No Easy Fix, But Important Awareness:**
    *   There isn't a simple switch to make `bs_greeks` output perfect Asian option greeks.
    *   The most important thing is **awareness and documentation**. Users of your system's output (whether a dashboard or a trading model) need to understand this nuance.
    *   The "Deep scan (assumptions & biases)" section in your `README.md` is a good place to mention this: "Assumes European option greeks approximate dealer hedging for Asian-settled Deribit options, which may not hold true near expiry."

**Recommendations for Your Build:**

1.  **Stick with European Models (for now):** Given the complexity and the likelihood that the market (and Deribit's quotes) operate on European approximations, your current approach (using Deribit's greeks if available, falling back to your Black-Scholes) is pragmatic.
2.  **Prioritize Robust Spot Price for BS:** Ensure `S` (spot price) used in `bs_greeks` is the most accurate and relevant underlying price (`spot[0]` in your processor, which comes from the index). This is correctly done.
3.  **Investigate Deribit's Greek Methodology (If Possible):** Try to find any documentation or community information on how Deribit calculates its published greeks. If they explicitly state it's Black-Scholes, then your system is consistent.
4.  **Parameter for Risk-Free Rate (`r`) and Dividends (`q`):**
    *   Currently, `r=0.0` is hardcoded when calling `bs_greeks`. For BTC, a "dividend yield" (e.g., from lending rates or basis) could be relevant (`q`). While often small for short-dated options, for longer ones or for high precision, these should be configurable or fetched from a source. For simplicity, `r=0`, `q=0` is a common starting point.
5.  **Option Type (`option_type` in `bs_greeks`):**
    *   Your processor correctly infers this from the instrument name (`-C-` or `-P-`). Ensure the numeric value (1 for Call, 0 for Put) aligns with what your `bs_greeks` function expects.
6.  **Documentation is Crucial:**
    *   Clearly state in your project's documentation that the greeks are based on European option models, and this is an approximation for Deribit's Asian-settled options.
    *   Explain the potential divergence near expiry and during the averaging period.
7.  **Future Enhancement (Advanced):**
    *   If the project becomes very advanced, you *could* explore:
        *   A flag or mode to switch to an Asian option pricer/greek calculator for instruments within X hours of their averaging period.
        *   Monitoring trading activity specifically *during* the averaging windows of major expiries.

**In summary:** The Asian nature of Deribit options is a critical detail. Your current approach of using European models (either Deribit's or your own Black-Scholes) is a common and practical starting point. The key is to be aware of the approximation, document it, and understand that the predicted dealer flows will be "European-equivalent" flows, which may differ from actual hedging for options very close to settlement. For most of an option's life, this approximation is likely acceptable for the kind of broad dealer flow analysis your system targets.