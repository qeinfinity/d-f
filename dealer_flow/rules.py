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
