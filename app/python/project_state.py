from dataclasses import dataclass, field
from ui_config import DEFAULT_COLORS

@dataclass
class Layer:
    name: str
    group: str
    data: object = None
    source: object = None
    visible: bool = False
    editable: bool = False
    dirty: bool = False
    column: str = ""
    low: float = -1.0
    high: float = 1.0
    colors: tuple = DEFAULT_COLORS
    color: str = "#459ed0"
    alpha: float = 1.0
    weights: dict = field(default_factory=dict)
    original_weights: dict = field(default_factory=dict)
    run_id: str = ""
    environment: str = ""
    original_iop: object = None
    modified: bool = False


