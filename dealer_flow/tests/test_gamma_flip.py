import pandas as pd
from dealer_flow.gamma_flip import gamma_flip_distance

def test_basic_flip():
    strikes = [9000, 9500, 10000, 10500]
    gamma = [-2.0, -1.0, 0.5, 1.2]
    series = pd.Series(gamma, index=strikes)
    assert gamma_flip_distance(series, 10000) == 0.05