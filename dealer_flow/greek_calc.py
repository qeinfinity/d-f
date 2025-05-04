"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.
All inputs are numpy arrays for vectorised speed.
"""
"""
Black-Scholes greeks (γ, vanna, charm, volga) with numba JIT.

Doctest sanity check
>>> import numpy as np; from dealer_flow.greek_calc import greeks
>>> γ, v, c, vg = greeks(np.array([100]), np.array([100]), np.array([0.1]), 0.0, np.array([0.5]), np.array([1]))
>>> round(float(γ), 6)
0.079788
"""
import numpy as np
from numba import njit
from scipy.stats import norm  # only used for cdf/pdf

SQRT_2PI = np.sqrt(2 * np.pi)

@njit(fastmath=True)
def _pdf(x):
    return np.exp(-0.5 * x * x) / SQRT_2PI

@njit(fastmath=True)
def _cdf(x):
    return 0.5 * (1.0 + np.erf(x / np.sqrt(2.0)))

@njit(fastmath=True)
def greeks(S, K, T, r, sigma, option_type):
    """
    Returns gamma, vanna, charm, volga for each row.
    """
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    pdf_d1 = _pdf(d1)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    
    # vanna = ∂^2 price / ∂S ∂σ
    vanna = -d2 * pdf_d1 / sigma
    
    # charm (dDelta/dt)
    charm = (
        -pdf_d1 * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
    )
    
    vega = S * pdf_d1 * np.sqrt(T)
    volga = vega * d1 * d2 / sigma
    
    return gamma, vanna, charm, volga
