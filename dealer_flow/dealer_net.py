"""
Infers dealer sign (MM vs customer) from open interest.
Assume dealer net pos = -customer_net_pos.
"""
import pandas as pd
import numpy as np

def infer_dealer_net(oi_df: pd.DataFrame) -> pd.DataFrame:
    """
    oi_df columns: ['instrument','type','open_interest','side']
    side: 'call_long','call_short','put_long','put_short'
    Returns df with dealer_gamma, dealer_vanna, ... per instrument
    """
    # Placeholder: mark all customer shorts as dealer long
    oi_df["dealer_side_mult"] = np.where(oi_df["side"].str.contains("short"), 1, -1)
    return oi_df
