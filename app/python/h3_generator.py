import re
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import h3
import pyogrio
from shapely import force_2d, make_valid
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from bdot_names import NAMES


TYPES = {
    "P": ("Point", "count"),
    "L": ("LineString", "length_m"),
    "A": ("Polygon", "area_m2"),
}


def parts(geometry, kind):
    """Wybiera części geometrii określonego typu."""
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [
        part
        for child in getattr(geometry, "geoms", [])
        for part in parts(child, kind)
    ]


def read_boundary(path):
    """Odczytuje granicę powiatu w EPSG:4326."""
    source = gpd.read_file(Path(path))
    if source.empty or source.crs is None:
        raise ValueError("Pusta granica lub brak CRS.")

    if "JPT_KOD_JE" in source.columns:
        codes = set(source["JPT_KOD_JE"].astype(str).str.strip())
        if codes != {"2005"}:
            raise ValueError(f"Oczekiwano powiatu hajnowskiego: {codes}")

    polygons = [
        polygon
        for geometry in source.to_crs(4326).geometry
        if geometry is not None and not geometry.is_empty
        for polygon in parts(make_valid(force_2d(geometry)), "Polygon")
    ]
    if not polygons:
        raise ValueError("Brak poligonów granicy.")
    return unary_union(polygons)


def generate_grid(boundary, resolution):
    """Generuje H3 w 4326; zwraca siatkę obliczeniową w 2180."""
    cells = h3.h3shape_to_cells_experimental(
        h3.geo_to_h3shape(mapping(boundary)),
        resolution,
        contain="overlap",
    )

    records = []
    for cell_id in sorted(cells):
        cell = Polygon([
            (longitude, latitude)
            for latitude, longitude in h3.cell_to_boundary(cell_id)
        ])
        polygons = parts(
            make_valid(cell.intersection(boundary)), "Polygon"
        )
        if polygons:
            geometry = unary_union(polygons)
            if geometry.area > 0:
                records.append({
                    "h3_id": cell_id,
                    "resolution": resolution,
                    "geom": geometry,
                })

    if not records:
        raise ValueError(f"Pusta siatka H3: {resolution}")

    grid = gpd.GeoDataFrame(
        records, geometry="geom", crs=4326
    ).to_crs(2180)

    grid["area_m2"] = grid.geometry.area
    if not grid.geometry.is_valid.all():
        raise ValueError("Niepoprawna geometria siatki.")
    return grid


def read_bdot(folder):
    """Odczytuje geometrie klas BDOT10K w EPSG:2180."""
    files = sorted(Path(folder).rglob("*.gpkg"))
    if not files:
        raise FileNotFoundError(f"Brak plików GPKG w {folder}")

    layers, used_names = {}, set()

    for path in files:
        for layer_name, geometry_type in pyogrio.list_layers(path):
            if geometry_type is None:
                continue

            match = re.search(
                r"OT_([A-Z0-9]+)_([ALP])$",
                str(layer_name).upper(),
            )
            if not match:
                raise ValueError(f"Nieznana klasa: {layer_name}")

            code, base, suffix = match.group(), *match.groups()
            if base not in NAMES:
                raise ValueError(f"Brak klasy {base} w bdot_names.py")

            name = f"{NAMES[base]}_{suffix}".lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,44}", name):
                raise ValueError(f"Niepoprawna lub za długa nazwa: {name}")
            if code in layers or name in used_names:
                raise ValueError(f"Powtórzona klasa albo nazwa: {code}")

            source = gpd.read_file(path, layer=layer_name)
            if source.crs is None or source.crs.to_epsg() != 2180:
                raise ValueError(f"{code}: wymagany EPSG:2180.")

            kind, _ = TYPES[suffix]
            geometries = []

            for geometry in source.geometry:
                if geometry is None or geometry.is_empty:
                    continue
                if geometry.geom_type not in {kind, f"Multi{kind}"}:
                    raise ValueError(f"{code}: niezgodny typ geometrii.")

                geometry = force_2d(geometry)
                if kind != "Point":
                    components = parts(make_valid(geometry), kind)
                    if not components:
                        raise ValueError(f"{code}: zdegradowana geometria.")
                    geometry = unary_union(components)

                geometries.append(geometry)

            layers[code] = {
                "name": name,
                "data": gpd.GeoDataFrame(
                    {"source_id": range(1, len(geometries) + 1)},
                    geometry=geometries,
                    crs=2180,
                ).rename_geometry("geom"),
            }
            used_names.add(name)
            print(f"Odczyt: {name}, obiekty: {len(geometries)}", flush=True)

    if not layers:
        raise ValueError("Brak przestrzennych klas BDOT10K.")
    return layers


def aggregate_grid(grid, layers, on_class=None):
    """Agreguje klasy w 2180; zwraca siatkę i geometrie klas w 4326."""
    if grid.crs.to_epsg() != 2180:
        raise ValueError("Agregacja wymaga EPSG:2180.")

    result = grid.sort_values("h3_id").reset_index(drop=True).copy()
    spatial_index = result.sindex
    vectors = {}

    for code, layer in sorted(layers.items()):
        kind, metric = TYPES[code[-1]]
        name = layer["name"]
        column = f"{name}_{metric}"
        values = [0 if kind == "Point" else 0.0 for _ in range(len(result))]
        fragments = defaultdict(list)

        for geometry in layer["data"].geometry:
            if kind == "Point":
                for point in parts(geometry, "Point"):
                    matches = sorted(
                        spatial_index.query(point, predicate="intersects")
                    )
                    if matches:
                        # Punkt graniczny trafia do jednego oczka.
                        i = int(matches[0])
                        values[i] += 1
                        fragments[i].append(point)
                continue

            matches = sorted(
                spatial_index.query(geometry, predicate="intersects")
            )
            remaining = geometry

            for index in matches:
                i = int(index)
                source = remaining if kind == "LineString" else geometry
                clipped = parts(
                    source.intersection(result.geometry.iloc[i]), kind
                )
                if not clipped:
                    continue

                clipped = unary_union(clipped)
                value = (
                    clipped.length if kind == "LineString"
                    else clipped.area
                )
                if value <= 0:
                    continue

                values[i] += value
                fragments[i].append(clipped)

                if kind == "LineString":
                    # Nie liczymy dwukrotnie fragmentu linii na granicy.
                    remaining = remaining.difference(clipped)
                    if remaining.is_empty:
                        break

        result[column] = values
        frame = gpd.GeoDataFrame(
            {
                "h3_id": result["h3_id"].tolist(),
                "bdot_code": [code] * len(result),
                column: values,
                "geom": [
                    unary_union(fragments[i]) if i in fragments else None
                    for i in range(len(result))
                ],
            },
            geometry="geom",
            crs=2180,
        ).to_crs(4326)

        if on_class is None:
            vectors[name] = frame
        else:
            on_class(name, frame)

        print(f"Agregacja: {name}", flush=True)

    # Transformujemy geometrię, nie wartości długości i powierzchni.
    return result.to_crs(4326), vectors