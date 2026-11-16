import numpy as np
import pandas as pd


def shown(value):
    if isinstance(value, (list, tuple, dict)):
        return str(value)
    if value is None or pd.isna(value):
        return "NULL"
    return f"{value:.6f}" if isinstance(value, (float, np.floating)) else str(value)


