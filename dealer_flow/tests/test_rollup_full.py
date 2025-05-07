# dealer_flow/tests/test_rollup_full.py
import numpy as np, pandas as pd
from dealer_flow.vanna_charm_volga import roll_up

def test_rollup_basic():
    df = pd.DataFrame(
        {
            "gamma":[2,-1],
            "vanna":[5,4],
            "charm":[-3,2],
            "volga":[6,3],
            "notional_usd":[1e6,8e5],
            "dealer_side_mult":[1,1],
        }
    )
    out = roll_up(df)
    assert out["NGI"] != 0 and out["VSS"] != 0