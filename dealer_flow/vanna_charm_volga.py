# dealer_flow/vanna_charm_volga.py
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def roll_up(
    dealer_greeks: pd.DataFrame,
    spot_pct: float = 0.01, # Standard 1% move for NGI, VSS, VOLG
) -> dict:
    """
    Aggregates dealer greeks to compute systemic risk metrics.
    Assumes dealer_greeks DataFrame contains:
        ['gamma', 'vanna', 'charm', 'volga', 'notional_usd', 'dealer_side_mult']
        where greeks are already dealer-signed (multiplied by dealer_side_mult).

    Returns:
        NGI (Net Gamma Impact): Dollar Gamma for a 1% spot move.
        VSS (Vanna Squeeze Size): Dollar Vanna for a 1% vol-spot move.
        CHL_24h (Charm Load): Net delta decay over 24 hours.
        VOLG (Volga Exposure): Dollar Volga for a 1% vol-spot move.
    """
    if dealer_greeks.empty:
        logger.warning("roll_up called with empty dealer_greeks DataFrame. Returning zero metrics.")
        return dict(NGI=0.0, VSS=0.0, CHL_24h=0.0, VOLG=0.0)

    # Ensure required columns exist, default to 0 if not (should not happen if processor is correct)
    required_cols = ['gamma', 'vanna', 'charm', 'volga', 'notional_usd']
    for col in required_cols:
        if col not in dealer_greeks.columns:
            logger.error(f"Missing required column '{col}' in dealer_greeks for roll_up. Defaulting to 0 for this column.")
            dealer_greeks[col] = 0.0
    
    # NGI: Net Gamma Impact for a 1% spot move.
    # Assumes 'gamma' is already dealer-signed.
    # Assumes 'notional_usd' is the notional value of the option contracts.
    # Gamma is d(Delta)/d(Spot), so Gamma * Spot is d(Delta)/d(Spot%)
    # Gamma * Spot * Spot_pct is d(Delta) for Spot_pct move.
    # NGI is sum(Gamma * Underlying_Price * Contracts * Spot_pct)
    # OR if notional_usd = Underlying_Price * Contracts, then NGI = sum(Gamma * notional_usd * Spot_pct)
    # Let's clarify based on how notional_usd is defined in processor.
    # processor: notional = open_interest * current_underlying_price (contracts * spot)
    # So, dollar_gamma per contract is gamma * spot_price.
    # For total position: gamma * spot_price * num_contracts = gamma * notional_usd
    # For a 1% move: gamma * notional_usd * spot_pct
    dealer_greeks["dollar_gamma_1pct"] = (
        dealer_greeks["gamma"] * dealer_greeks["notional_usd"] * spot_pct
    )
    NGI = dealer_greeks["dollar_gamma_1pct"].sum()
    
    # VSS: Vanna Squeeze Size – hedge quantity for 1 % vol and 1% spot move.
    # Vanna is d(Delta)/d(Vol) or d(Vega)/d(Spot).
    # Dollar Vanna for 1% vol change: Vanna * Notional * 0.01 (if Vanna is per 1 unit vol change)
    # The spot_pct here is for consistency if interpreting VSS as sensitivity to correlated move.
    VSS = (dealer_greeks["vanna"] * dealer_greeks["notional_usd"] * 0.01).sum() # 0.01 for 1% change in IV

    # CHL_24h: Charm Load – net delta decay over 24 hours.
    # Charm is d(Delta)/d(Time). If T is in years, Charm is per year.
    # Daily charm = Charm_per_year * (1 day / 365 days)
    # Notional impact: Daily_Charm * Notional
    CHL_24h = (
        dealer_greeks["charm"] * dealer_greeks["notional_usd"] * (1 / 365.0)
    ).sum()

    # VOLG: Volga Exposure – convexity of Vega w.r.t vol. d(Vega)/d(Vol).
    # Dollar Volga for 1% vol change: Volga * Notional * 0.01
    VOLG = (dealer_greeks["volga"] * dealer_greeks["notional_usd"] * 0.01).sum() # 0.01 for 1% change in IV
    
    return dict(NGI=NGI, VSS=VSS, CHL_24h=CHL_24h, VOLG=VOLG)

#     *Self-correction during thought*: The VSS and VOLG terms are sensitivities to Implied Volatility (IV). So the `* 0.01` should represent a 1% change in IV (e.g., from 50% to 51%), not related to `spot_pct`. My previous `roll_up` was using `spot_pct` for VSS and VOLG, which is less standard if they are meant to reflect pure IV sensitivity. I've changed it to `* 0.01` to represent a 1 percentage point change in IV. NGI correctly uses `spot_pct`.
