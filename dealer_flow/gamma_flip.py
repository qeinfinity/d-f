import numpy as np
import pandas as pd
from typing import Optional


def gamma_flip_distance(
    gamma_by_strike: pd.Series, spot_price: float
) -> Optional[float]:
    """
    gamma_by_strike: index=strike, value=net dealer gamma
    Finds first zero-cross and returns (strike/spot - 1)
    """
    signs = np.sign(gamma_by_strike.values)
    zero_idx = np.where(np.diff(signs))[0]
    if zero_idx.size == 0:
        return None
    flip_strike = gamma_by_strike.index[zero_idx[0] + 1]
    if spot_price == 0:
        return None
    return float(flip_strike / spot_price - 1.0)