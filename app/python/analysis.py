import math
import numpy as np
import pandas as pd
from bdot_names import NAMES
from bdot_weights import WEIGHTS

def normalized_weights(frame, weights=None):
    """Dokładne dopasowanie kolumn agregacji do słownika, bez cichego pomijania."""
    weights = WEIGHTS if weights is None else weights
    lookup = {}
    for code, name in NAMES.items():
        for suffix, metric in (("a", "area_m2"), ("l", "length_m"), ("p", "count")):
            column = f"{name}_{suffix}_{metric}_norm".lower()
            weight = float(weights[code])
            if column in lookup and lookup[column] != weight:
                raise ValueError(f"Sprzeczne wagi aliasów dla {column}.")
            lookup[column] = weight
    columns = [c for c in frame.columns if c.endswith(("_area_m2_norm", "_length_m_norm", "_count_norm"))]
    missing = set(columns) - set(lookup)
    if missing:
        raise ValueError("Brak dopasowania wag: " + ", ".join(sorted(missing)))
    return {c: lookup[c] for c in columns}


def calculate_iop(frame, weights):
    active = {c: w for c, w in weights.items() if w != 0}
    if any(not math.isfinite(w) or not -1 <= w <= 1 for w in weights.values()):
        raise ValueError("Wagi muszą należeć do [-1, 1].")
    if not active:
        return pd.Series(np.nan, index=frame.index)
    values = frame[list(active)].apply(pd.to_numeric, errors="raise")
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all() or (array < 0).any() or (array > 1).any():
        raise ValueError("Kolumny _norm muszą zawierać kompletne wartości od 0 do 1.")
    return values.mul(pd.Series(active), axis=1).sum(axis=1) / len(active)


