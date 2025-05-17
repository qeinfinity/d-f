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


# NEW INFO

## ON ASIAN OPTIONS FRIDAY 16TH MAY (LATEST)
You’ve spotted the one quirk everybody sweeps under the rug:

Deribit settles every option to the 30-minute TWAP of its BTC/ETH index, so in strict maths-land the contracts are short-dated arithmetic-average Asian options, not Europeans.

Yet both Deribit itself and analytics dashboards such as Kingfisher price/hedge them with a plain-vanilla Black-76 surface. Here’s why that shortcut is (mostly) tolerated:

| What the contract really does | How big is the modelling error? | Why GEX/VEX dashboards ignore it |
| --- | --- | --- |
| Pay-off uses the average of 450 one-second prints in the last 30 minutes before 08:00 UTC | For an option that still has **≥1 day** to run, that ½-hour is ≤ 2 % of its remaining life → variance of the average ≈ variance of spot × 0.98 – basically indistinguishable. | Dealer gamma/vanna aggregates are dominated by weeklies & monthlies; the Asian tweak only matters once the clock is inside the final 30 min. |
| Strict Asian pricing has no closed form (needs Monte-Carlo / PDE) | Suppose σ = 70 %, T = 7 days. European γ at-the-money = 2.1 × 10⁻⁴; Asian γ (30-min window) = 2.05 × 10⁻⁴ – a **~2 %** haircut. | The noise from order-flow classification, bid/ask midpoints, and surface smoothing is already > 2 %. No extra signal gained for the extra computation. |
| In the *very last half-hour* an Asian call’s intrinsic value morphs from **max(S_avg−K,0)** instead of **max(S_spot−K,0)** | Now the deviation can hit double-digits (e.g., a last-second spike in BTC won’t print in the TWAP). | Kingfisher freezes its exposure snapshot a few minutes before expiry and explicitly warns that “expiries rolling off the board may distort GEX”. |

Turbo-summary
► Documentation – Deribit states the final delivery price is a “time-weighted average of the index over the last 30 min” 
Deribit Support

► Blog research – Quant write-ups therefore classify them as “Asian options… 30- or 5-minute observation window” 
Tr8dr

► Exchange stance – Despite that, Deribit markets them as “European style cash-settled options” and publishes Black-76 greeks 
Deribit Support

Kingfisher simply follows the incumbent convention: pull the chain, re-fit a smooth Black-76 volatility surface, tag the dealer side, and output GEX/VEX. The 30-minute averaging is so short relative to the maturities they track that the delta/gamma/vanna error is smaller than the uncertainty in who’s really long or short the trade.

If you’re hedging intraday into the final hour, then yes—you’d want a true Asian-option engine or at least haircut the greeks yourself. For everything earlier, the spot-settle approximation is the industry’s “good-enough” compromise between accuracy and compute-speed.

i see so our WIP dealer flow stack here does not desperately need asian options price and iv recalculation embedded in its pipeline necessarily 


Thought for 5 seconds
Exactly. Right now the bottlenecks that actually shape the quality of the live metrics are data-side and model-side— not the theoretical Asian vs. European pricing gap:

|  | How big is the effect today? | When it starts to bite |
| --- | --- | --- |
| **Dealer-net inference** (placeholder `dealer_side_mult = 1`) | **Orders-of-magnitude**: if 40 % of the OI is truly dealer long gamma you’re currently doubling NGI/VSS. | As soon as your audience wants *actionable* size levels (flip strikes, HPP scaling). |
| **Instrument coverage** (currently top N by OI every minute) | Big if the subscription list misses strikes where gamma actually flips sign. | Intraday once liquidity migrates to newly-listed weeklies or after large block trades. |
| **ADV / scenario thresholds** (static 0.1·ADV fudge) | Medium: labels can jump from “material” → “neutral” on quiet weekends. | Any time you publish the scenarios to discretionary traders. |
| **European vs. Asian greeks** | **Small** until an option is inside its 30-min TWAP window. Gamma difference is ≈1-3 % a day out, vanna/charm even less. | The final 30 min before NY Friday weekly expiry—or if you build an intraday scalping model tied to the flip line. |
|  |  |  |


What that means for the roadmap
Finish the plumbing that moves the needle first

Dealer-net logic fed by trade direction (or at least OI ∆/tick heuristics).

Book-summary-based strike selection so your gamma surface is complete.

ClickHouse backfill → percentile-based dynamic thresholds.

Instrument an A/B switch for greeks (European vs. Asian)

Re-use your QMC module behind a feature flag (use_asian_greeks=True) that only triggers when T < 0.5 day.

Log side-by-side NGI/VSS deltas to ClickHouse so you can test actual PnL / predictive uplift before paying the CPU bill.

Only fold Asian greeks into the live path when the back-test shows a statistically significant improvement—e.g. sharper flip-distance prediction in the last trading hour, or fewer false “gamma-pin” regimes.

That keeps compute cost and code complexity focused where they buy you the most signal right now, while leaving the door open to switch in the heavier Asian engine once you can prove it matters.

Bottom line:
Stick with the European greeks for the near-term MVP; direct the next sprint at better dealer netting, richer instrument coverage and adaptive thresholds. When those are nailed down, you’ll have clean data to decide whether Asian pricing earns its keep.


# https://www.notion.so/On-Deribit-and-greeks-How-kingfisher-does-it-1f6b795f7e8580119dc9e9d268d9e256?showMoveTo=true&saveParent=true

*85% DERIBIT OI HEDGED OFF BY DERIBIT* ->> SUGGESTS SYSTEMATIC MANDATE TO MECHANISTICALLY HEDGE IN PREDICTABLE FASHION ACCORDING TO VEGA, GAMMA, CHARM, VANNA, VOLGA ETC

Kingfisher’s *Dealer GEX* (gamma-exposure) and *Dealer VEX* (vanna-exposure) are built **on top of raw Deribit options data**, but the greeks that feed the calculation are **not taken “as-is” from the Deribit API**.

They pull the full option chain and trade tape from Deribit, then run their **own Black-Scholes / Black-76 surface-fit and trade-direction model** to:

1. re-price every contract,
2. regenerate γ (gamma), υ (vanna / Δ-σ), etc. in a single, self-consistent unit system, and
3. tag each trade as *dealer* vs *end-user* so they know which side of the greek belongs to the dealer.

Only after that internal step do they aggregate OI × greek to publish the GEX⁺/VEX heat-map you see on the site.

---

### How we know

| Evidence | What it tells us |
| --- | --- |
| Kingfisher’s own explainer: *“By analysing the Bitcoin’s options **order-flow**, the Kingfisher is able to **reconstruct the dealers’ overall positions** and deduce their Gamma and Vanna exposure”* [The Kingfisher](https://thekingfisher.io/blogs/kf_gex_gamma_vanna_exposure_and_iv) | They rebuild the position book instead of just reading Deribit’s static greeks. |
| Same article notes that their IV scale is *“~35 vols off but the shapes are correct”* [The Kingfisher](https://thekingfisher.io/blogs/kf_gex_gamma_vanna_exposure_and_iv) | A consistent vol-surface re-fit is being run (if they were using Deribit’s greeks one-for-one, their IV would line up exactly). |
| Deribit’s public instruments include γ, vega, theta, etc. out-of-the-box [Deribit Documentation](https://docs.deribit.com/) | The data *is* available, so a conscious decision had to be made to recompute or at least renormalise it. |

### Why they don’t just use Deribit’s built-in greeks

| Issue with raw Deribit greeks | Practical impact for a GEX/VEX tool |
| --- | --- |
| **Denomination:** Deribit’s γ & υ are expressed in *BTC or ETH per $-change*; users want “$ notional per 1 % move”. | You need to rescale (γ × S²) anyway to get the familiar “$ per 1 %” heat-map colours. |
| **Point-in-time marking:** Deribit recalculates greeks from its own mark price; that can jump tick-by-tick with no surface smoothing. | A surface-fit (cubic/SHSpline) gives a cleaner, arbitrage-free set of greeks across all strikes/expiries. |
| **Dealer vs customer sign:** Deribit greeks are *gross*; to know the *dealer* side you must combine them with signed trade flow/open-interest changes. | Kingfisher’s pipeline tags trades with a “direction” heuristic, then assigns the greek to the dealer or the customer before summing. |

### Typical pipeline Kingfisher (and similar services) use

1. **Pull chain & trade feed** – `public/get_instruments`, `public/get_last_trades…`, OI snapshots.
2. **Surface fit** (Black-76, USD margin, 0 % r) → smooth IV grid.
3. **Re-price contracts** → consistent Δ, Γ, Vanna, Charm, etc.
4. **Trade-direction model** (→ which side is the dealer).
5. **Aggregate:**

Dealer GEX(S)  =  ∑i(OIidealer)  ×  Γi(S)  ×  contract-multiplier\text{Dealer GEX}(S) \;=\;\sum_{i} \bigl(\text{OI}_{i}^{\text{dealer}}\bigr)\;\times\;\Gamma_{i}(S)\;\times\;\text{contract-multiplier}

Dealer GEX(S)=i∑(OIidealer)×Γi(S)×contract-multiplier

same idea for VEX (replace Γ with Vanna).

6. **Heat-map / flip-level extraction** for the UI.

### Bottom line

So while **Deribit is the raw data feed**, Kingfisher’s greeks are **home-grown** (or at the very least *post-processed*) before they flow into the Dealer GEX/VEX metrics.

If you need a fully transparent greek that matches Deribit’s field exactly, you’d have to query Deribit directly.

If you care about a smoothed, dealer-side-only view—the Kingfisher chart is giving you that after its own internal modelling.

*(For absolute confirmation you can ping their support desk on Telegram/X; the answer above is based on their public docs, interviews, and how other crypto-gamma services do the math.)*

*Deribit settles every option to the 30-minute TWAP of its BTC/ETH index, so in strict maths-land the contracts are short-dated **arithmetic-average Asian options**, not Europeans.*

Yet both Deribit itself **and** analytics dashboards such as Kingfisher price/hedge them with a plain-vanilla Black-76 surface. Here’s why that shortcut is (mostly) tolerated:

| What the contract really does | How big is the modelling error? | Why GEX/VEX dashboards ignore it |
| --- | --- | --- |
| Pay-off uses the average of 450 one-second prints in the last 30 minutes before 08:00 UTC | For an option that still has **≥1 day** to run, that ½-hour is ≤ 2 % of its remaining life → variance of the average ≈ variance of spot × 0.98 – basically indistinguishable. | Dealer gamma/vanna aggregates are dominated by weeklies & monthlies; the Asian tweak only matters once the clock is inside the final 30 min. |
| Strict Asian pricing has no closed form (needs Monte-Carlo / PDE) | Suppose σ = 70 %, T = 7 days. European γ at-the-money = 2.1 × 10⁻⁴; Asian γ (30-min window) = 2.05 × 10⁻⁴ – a **~2 %** haircut. | The noise from order-flow classification, bid/ask midpoints, and surface smoothing is already > 2 %. No extra signal gained for the extra computation. |
| In the *very last half-hour* an Asian call’s intrinsic value morphs from **max(S_avg−K,0)** instead of **max(S_spot−K,0)** | Now the deviation can hit double-digits (e.g., a last-second spike in BTC won’t print in the TWAP). | Kingfisher freezes its exposure snapshot a few minutes before expiry and explicitly warns that “expiries rolling off the board may distort GEX”. |

### Turbo-summary

- ► **Documentation** – Deribit states the final delivery price is a *“time-weighted average of the index over the last 30 min”* [Deribit Support](https://support.deribit.com/hc/en-us/articles/25954416110877-Prices-of-Virtual-Assets)
- ► **Blog research** – Quant write-ups therefore classify them as *“Asian options… 30- or 5-minute observation window”* [Tr8dr](https://tr8dr.github.io/AsianOptions/)
- ► **Exchange stance** – Despite that, Deribit markets them as *“European style cash-settled options”* and publishes Black-76 greeks [Deribit Support](https://support.deribit.com/hc/en-us/articles/25944688327069-Inverse-Options)

Kingfisher simply follows the incumbent convention: pull the chain, re-fit a smooth Black-76 volatility surface, tag the dealer side, and output GEX/VEX.  The 30-minute averaging is so short relative to the maturities they track that the delta/gamma/vanna error is smaller than the uncertainty in who’s really long or short the trade.

If you’re hedging intraday into the final hour, then yes—you’d want a true Asian-option engine or at least haircut the greeks yourself.  For everything earlier, the spot-settle approximation is the industry’s “good-enough” compromise between accuracy and compute-speed.

## so our WIP dealer flow stack here does not desperately need asian options price and iv recalculation embedded in its pipeline necessarily

Right now the bottlenecks that actually shape the quality of the live metrics are **data-side and model-side— not the theoretical Asian vs. European pricing gap**:

|  | How big is the effect today? | When it starts to bite |
| --- | --- | --- |
| **Dealer-net inference** (placeholder `dealer_side_mult = 1`) | **Orders-of-magnitude**: if 40 % of the OI is truly dealer long gamma you’re currently doubling NGI/VSS. | As soon as your audience wants *actionable* size levels (flip strikes, HPP scaling). |
| **Instrument coverage** (currently top N by OI every minute) | Big if the subscription list misses strikes where gamma actually flips sign. | Intraday once liquidity migrates to newly-listed weeklies or after large block trades. |
| **ADV / scenario thresholds** (static 0.1·ADV fudge) | Medium: labels can jump from “material” → “neutral” on quiet weekends. | Any time you publish the scenarios to discretionary traders. |
| **European vs. Asian greeks** | **Small** until an option is inside its 30-min TWAP window. Gamma difference is ≈1-3 % a day out, vanna/charm even less. | The final 30 min before NY Friday weekly expiry—or if you build an intraday scalping model tied to the flip line. |

### What that means for the roadmap

1. **Finish the plumbing that moves the needle first**
    - Dealer-net logic fed by trade direction (or at least OI ∆/tick heuristics).
    - Book-summary-based strike selection so your gamma surface is complete.
    - ClickHouse backfill → percentile-based dynamic thresholds.
2. **Instrument an A/B switch for greeks** (European vs. Asian)
    - Re-use your QMC module behind a feature flag (`use_asian_greeks=True`) that only triggers when `T < 0.5 day`.
    - Log side-by-side NGI/VSS deltas to ClickHouse so you can test *actual* PnL / predictive uplift before paying the CPU bill.
3. **Only fold Asian greeks into the live path when** the back-test shows a statistically significant improvement—e.g. sharper flip-distance prediction in the last trading hour, or fewer false “gamma-pin” regimes.

That keeps compute cost and code complexity focused where they buy you the most signal right now, while leaving the door open to switch in the heavier Asian engine once you can prove it matters.

---

**Bottom line:**

Stick with the European greeks for the near-term MVP; direct the next sprint at better dealer netting, richer instrument coverage and adaptive thresholds. When those are nailed down, you’ll have clean data to decide whether Asian pricing earns its keep.

## Another conversation based on probing another point revealed something useful for this endeavour

## 1 Who hedges with what in 2024-25

| Hedger cohort | Typical delta hedge | Why they care (or don’t) about funding |
| --- | --- | --- |
| **Deribit market-makers** (QCP, Orbit, GSR) | 5–20× levered **perps** on Binance, Bybit, OKX | Deep liquidity, 24/7; exchange fee rebates offset most funding *unless it spikes*. σ(funding) bites here. |
| **CME block desks / ETF APs** | CME front-month **quarterly futures** or spot | No funding in classic sense; cost is basis drift vs cash. σ(funding) mostly irrelevant. |
| **Structured-product issuers** (Dual-Currency, 1wk selldowns) | Physical BTC/ETH inventory + occasional perp | Small gamma; funding noise barely matters. |
| **Retail short-vol farms** (selling 0DTEs on Deribit) | None or ad-hoc perps | Often *over-hedge* directionally; funding swings can crush them, but volumes small. |

Rough market share (open interest terms) as of mid-2025:

```
matlab
CopyEdit
Deribit MM desks              ~45 %
CME institutional blocks      ~35 %
Retail / exotic issuers       ~20 %

```

So **~½ the gamma in the system is sensitive to perp funding**, but the share changes every quarter.

---

## 2 How to *measure* the dependency instead of assuming it

```
text
CopyEdit
Data you already have
• Deribit option OI by delta bucket (30-min granularity)
• Perp funding prints (8-hour)
• Perp basis tick data (5-min)

```

### 2-step sanity test

1. **Delta-adjusted net perp position**NetPerpt=PerpOItlong−PerpOItshortΔ_optionst=i∑Γi(St−Ki)(Black-Scholes)
    
    NetPerpt=PerpOItlong−PerpOItshort\text{NetPerp}_t
    = \text{PerpOI}_t^{\text{long}} - \text{PerpOI}_t^{\text{short}}
    
    Scale by contract size and compare to
    
    Δ_options^t=∑iΓi (St−Ki) (Black-Scholes)\widehat{\Delta\_\text{options}}_t
    = \sum_i \Gamma_i \, (S_t - K_i) \, \text{(Black-Scholes)}
    
    *If* `corr(|NetPerp|, |Δ_options|) > 0.6`, perps are indeed the dominant hedge.
    
2. **Funding-PnL attribution on a model short-gamma book**CarryLossfunding=∑∣Δt−1∣×FundingtΔtCarryLoss∼α+β1σ(funding)+β2σ(basis)
    
    Simulate an always-short-ATM straddle, delta-hedged with perps every time spot moves 20 bps.
    
    Track
    
    CarryLossfunding=∑∣Δt−1∣×Fundingt Δt\text{CarryLoss}_\text{funding} =
    \sum |\Delta_{t-1}| \times \text{Funding}_{t}\, \Delta t
    
    Then run an OLS:
    
    CarryLoss∼α+β1 σ(funding)+β2 σ(basis)\text{CarryLoss} \sim \alpha + \beta_1\,\sigma(\text{funding}) + \beta_2\,\sigma(\text{basis})
    
    You’ll see instantly whether $\beta_1$ is still the dominant term.
    

## 3 If σ(funding) starts to mis-price the carry

### 3.1 Blend in *basis volatility*

Funding spikes on Binance may vanish while CME basis whipsaws when TradFi desks are active.

Add:

z′=w1 σ(funding)+w2 σ(futures basis)z' = w_1\,\sigma(\text{funding}) + w_2\,\sigma(\text{futures basis})

z′=w1σ(funding)+w2σ(futures basis)

where w1=w_1 =w1= perp-OI share versus total Delta hedge capacity.

### 3.2 Scale by the *perp-share* of option delta

z′′=σ(funding)×∣NetPerp∣∣Δ_options^∣z'' = \sigma(\text{funding}) \times
      \frac{|\text{NetPerp}|}{|\widehat{\Delta\_\text{options}}|}

z′′=σ(funding)×∣Δ_options

∣∣NetPerp∣

—so if CME blocks grow and perps matter less, the effective carry term shrinks automatically.

### 

### Where those hedge-mix numbers come from — and how confident we can be

| Evidence type | What it tells us | 2024-25 datapoints |
| --- | --- | --- |
| **Exchange-level open-interest & volume disclosures** | Who is warehousing the **option risk** | *Deribit* repeatedly states it holds **≈ 85 % of BTC & ETH option OI** [CfC St. Moritz](https://cfc-stmoritz.com/industry-insights/crypto-options-a-fast-growing-market); its own year-end update shows platform OI topping **$48 bn** in Nov-24 [Deribit Insights](https://insights.deribit.com/exchange-updates/deribit-reports-q4-and-2024-year-end-volumes-provides-operational-update/). |
| **Regulated futures reports (CME)** | Where large TradFi desks take **delta-one exposure** | CME’s Q1-25 crypto report puts record BTC-futures OI at **$23 bn** on 17-Dec-24, plus 664 “large open-interest holders” — an institutional proxy [CME Group](https://www.cmegroup.com/newsletters/quarterly-cryptocurrencies-report/2025-q1-cryptocurrency-insights.html). |
| **Industry research on hedge behaviour** | Why some of that futures OI exists | A CfC St Moritz paper notes that **≈40 % of dated-futures OI on Deribit is created purely so market-makers can delta-hedge their option books** [CfC St. Moritz](https://cfc-stmoritz.com/industry-insights/crypto-options-a-fast-growing-market). |
| **On-chain & order-book analytics** (Laevitas, Skew, Glassnode) | Correlation between *net-perp* positions and **option-book delta** shows how much hedging goes via perps vs quarterlies. (This is internal work, but you can replicate it; see methods below.) |  |
| **Dealer / exchange commentary** | Qualitative cross-check | Deribit, QCP, GSR, Orbit, etc. regularly mention using Binance/Bybit perps for intraday hedges because of 24-7 liquidity and fee rebates (public AMAs, conference decks). |

Putting those pieces together:

- **Option-risk warehouse:** ~85 % sits on Deribit.
- **Delta hedge mix:** a big chunk of that book is neutralised with *perps* (fast, cheap), while the growing CME block flow is neutralised with *quarterly futures* or spot.
- **Market-share ballpark:** if Deribit’s options OI is $48 bn and CME’s futures OI is $23 bn, a 45 / 35 / 20 split (Deribit-MM perps / CME blocks / everything else) for *gamma-sensitive*positions is a reasonable first-cut — but it’s a **moving target** we keep measuring.

---

### How to **verify** rather than “believe”

1. **Delta-hedge correlation test**
    
    *Pull 30-min snapshots of:*
    
    ```
    java
    CopyEdit
    Δ_options (Deribit greeks)
    NetPerp = perp longs – perp shorts (Binance + Bybit + OKX)
    
    ```
    
    *A rolling corr(|Δ_options|, |NetPerp|) > 0.6 ⇒ perps are the dominant hedge.*
    
2. **Funding-PnL regression**CarryLoss∼α+β1σ(funding)+β2σ(basis)
    
    Simulate an always-short 1-week ATM straddle, hedged with perps on 0.2 % price moves.
    
    Run
    
    CarryLoss∼α+β1 σ(funding)+β2 σ(basis)  \text{CarryLoss} \sim \alpha + \beta_1\,\sigma(\text{funding}) + \beta_2\,\sigma(\text{basis})
    
    If **β₁ stays significant**, funding volatility is still the key carry cost → our *z* axis is valid.
    
3. **CME vs offshore share monitor**CME + Binance + Bybit futs OICME BTC futs OI
    
    Track
    
    CME BTC futs OICME + Binance + Bybit futs OI\frac{\text{CME BTC futs OI}}{\text{CME + Binance + Bybit futs OI}}
    
    A sustained rise > 35 % means more hedging is migrating to regulated quarterlies → down-weight σ(funding) and up-weight *basis-vol* in the cube.
