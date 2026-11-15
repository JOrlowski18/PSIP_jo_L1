import json
import math
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
from shapely.geometry import Point
from sqlalchemy import URL, create_engine, text
from matplotlib.figure import Figure
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Patch
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar


from ui_config import (APP_LOGIN, APP_PASSWORD, WINDOW_SIZE, SIDEBAR_WIDTH, BUTTON_COLUMNS, FONT, SCHEMAS, ENVIRONMENTS, IOP, MAP_CRS, DEFAULT_COLORS, THEMES, TOOLS, GEOD, TO_WGS, TO_WEB, CLASS_ORDER)
from project_state import Layer
from data_access import docker_url, prepare, read_result_layer
from analysis import calculate_iop, normalized_weights

def shown(value):
    if isinstance(value, (list, tuple, dict)):
        return str(value)
    if value is None or pd.isna(value):
        return "NULL"
    return f"{value:.6f}" if isinstance(value, (float, np.floating)) else str(value)


