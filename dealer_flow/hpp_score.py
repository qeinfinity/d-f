def hpp(spot_move_sign: int, NGI: float, VSS: float, CHL: float, alpha=0.1, beta=0.1):
    """
    Hedge-Pressure Projection
    """
    return spot_move_sign * NGI + alpha * VSS + beta * CHL
