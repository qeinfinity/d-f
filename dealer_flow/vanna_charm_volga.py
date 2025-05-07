import pandas as pd

def roll_up(
    dealer_greeks: pd.DataFrame,
    spot_pct: float = 0.01,
) -> dict:
    """
    dealer_greeks columns: ['gamma','vanna','charm','volga','notional_usd']
    Returns NGI, VSS, CHL_24h, VOLG
    """
    # Dollar gamma for 1% move
    dealer_greeks["dollar_gamma"] = (
        dealer_greeks["gamma"] * dealer_greeks["notional_usd"] * spot_pct
    )
    NGI = dealer_greeks["dollar_gamma"].sum()
    
    # Vanna Squeeze Size – hedge quantity for 1 % vol–spot move
    VSS = (dealer_greeks["vanna"] * spot_pct * dealer_greeks["notional_usd"]).sum()
    # Charm Load – daily theta hedge need
    CHL = (
        dealer_greeks["charm"] * 24 / 365 * dealer_greeks["notional_usd"]
    ).sum()
    # Volga Exposure – convexity w.r.t vol
    VOLG = (dealer_greeks["volga"] * spot_pct * dealer_greeks["notional_usd"]).sum()
    
    return dict(NGI=NGI, VSS=VSS, CHL_24h=CHL, VOLG=VOLG)
