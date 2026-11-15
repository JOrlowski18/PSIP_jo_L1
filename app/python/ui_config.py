from pyproj import Geod, Transformer

APP_LOGIN = "admin"
APP_PASSWORD = "psip"
WINDOW_SIZE = "1450x900"
SIDEBAR_WIDTH = 370
BUTTON_COLUMNS = 8
FONT = ("Arial", 10)
SCHEMAS = ("results_r7", "results_r8", "results_r9")
ENVIRONMENTS = ("env-test-js-db", "env-qa-jo-db", "main", "local")
IOP = "wsp_iop_norm"
MAP_CRS = 2180
DEFAULT_COLORS = ("#d7191c", "#ffffff", "#1a9641")
THEMES = {
    "Jasny": dict(bg="#f1f1f1", panel="#ffffff", fg="#181818", select="#cbd8e6", map="#d3d6da", button="#e5e5e5", active="#c6d6e6", muted="#646464"),
    "Ciemny": dict(bg="#080808", panel="#171717", fg="#f2f2f2", select="#4b4b4b", map="#303030", button="#282828", active="#484848", muted="#b3b3b3"),
}
# Menu oraz pasek narzędzi: kolejność i podpisy dostosuj tutaj.
MENUS = {
    "Plik": [("Sesja aplikacji", "session_dialog"), ("PostgreSQL", "database_dialog"),
             ("Wczytaj SHP", "load_shp"), ("Eksport PDF", "pdf_dialog"), ("Scenariusz", "scenario_dialog")],
    "Analiza": [("Odległość", "measure_dialog"), ("Współrzędne", "coordinates_dialog"),
                ("Wagi / analiza", "weights_dialog"), ("Szukaj", "search_dialog")],
    "Misc": [("Motyw", "theme_dialog")],
}
TOP_TOOLS = [("Styl", "style_dialog", "style"), ("Zoom do obiektu", "zoom_dialog", "target"),
             ("Warstwa punktowa", "points_dialog", "point"), ("Legenda", "legend_dialog", "legend")]
MAP_TOOLS = [("Całość", "home", "home"), ("Wstecz", "back", "left"), ("Dalej", "forward", "right"),
             ("Przesuń", "pan", "pan"), ("Powiększ", "zoom", "zoom")]
# Przestawiaj pozycje tutaj, aby zmienić układ przycisków.
TOOLS = [
    ("Sesja aplikacji", "session_dialog"), ("PostgreSQL", "database_dialog"),
    ("Wczytaj SHP", "load_shp"), ("Warstwy", "layers_dialog"),
    ("Wagi / analiza", "weights_dialog"), ("Styl", "style_dialog"),
    ("Szukaj", "search_dialog"), ("Zoom do obiektu", "zoom_dialog"),
    ("Odległość", "measure_dialog"), ("Warstwa punktowa", "points_dialog"),
    ("Współrzędne", "coordinates_dialog"), ("Legenda", "legend_dialog"),
    ("Motyw", "theme_dialog"), ("Eksport PDF", "pdf_dialog"),
    ("Scenariusz", "scenario_dialog"),
]
GEOD = Geod(ellps="WGS84")
TO_WGS = Transformer.from_crs(MAP_CRS, 4326, always_xy=True)
TO_WEB = Transformer.from_crs(MAP_CRS, 3857, always_xy=True)



from bdot_names import NAMES
CLASS_ORDER = {f"{name}_{suffix}".lower(): order for order,name in enumerate(dict.fromkeys(NAMES.values())) for suffix in "alp"}
