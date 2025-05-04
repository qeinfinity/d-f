"""
Infers dealer sign (MM vs customer) from open interest.
Assume dealer net pos = -customer_net_pos.
"""
import pandas as pd
import numpy as np

def infer_dealer_net(oi_df: pd.DataFrame) -> pd.DataFrame:
    """
    oi_df may contain:
        ['instrument', 'gamma', 'vanna', 'charm', 'volga', 'notional_usd', ...]
    Optionally:
        ['side'] with values like 'call_long', 'call_short', etc.

    Returns same DF with a 'dealer_side_mult' column (1 or -1).
    """
    if "side" in oi_df.columns:
        oi_df["dealer_side_mult"] = np.where(
            oi_df["side"].str.contains("short"), 1, -1
        )
    else:
        # no side info yet – assume dealer needs to hedge ALL customer gamma
        oi_df["dealer_side_mult"] = 1

    return oi_df
