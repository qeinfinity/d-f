# dealer_flow/dealer_net.py
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def infer_dealer_net(oi_df: pd.DataFrame) -> pd.DataFrame:
    """
    Infers dealer sign (MM vs customer) from open interest.
    ASSUMPTION (v0.3): Without actual trade flow data, this is a major simplification.
    The 'side' column is NOT currently populated by the processor from ticker/book data.
    Therefore, 'dealer_side_mult' defaults to 1, assuming all OI represents
    positions that dealers would need to hedge as if they were short gamma against them
    (e.g., customer is long the option).

    A more sophisticated model would require trade data analysis.
    """
    if "side" in oi_df.columns and not oi_df["side"].empty: # Check if 'side' actually has data
        logger.info("Attempting dealer netting using 'side' column.")
        oi_df["dealer_side_mult"] = np.where(
            oi_df["side"].str.contains("short", case=False, na=False), 1, -1
        ) # Assuming 'short' in side means customer is short, dealer is long. Adjust if interpretation differs.
    else:
        logger.debug("No 'side' column in OI data or it's empty; defaulting dealer_side_mult to 1 (assume dealer short gamma exposure on all OI).")
        oi_df["dealer_side_mult"] = 1
    return oi_df