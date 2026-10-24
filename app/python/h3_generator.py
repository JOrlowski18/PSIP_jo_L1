import argparse
from pathlib import Path

import geopandas as gpd
import h3
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union


def polygon_parts(geometry):
    """Zwraca części poligonowe, pomijając linie i punkty."""
    if geometry.is_empty:
        return []

    if isinstance(geometry, Polygon):
        return [geometry]

    if hasattr(geometry, "geoms"):
        return [
            polygon
            for part in geometry.geoms
            for polygon in polygon_parts(part)
        ]

    return []


def read_boundary(path):
    """Wczytuje granicę i przelicza ją do WGS84 wymaganego przez H3."""
    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku: {path}")

    source = gpd.read_file(path)

    if source.empty:
        raise ValueError("Plik granicy nie zawiera obiektów.")

    if source.crs is None:
        raise ValueError("Brak układu współrzędnych. Sprawdź plik .prj.")

    source = source.to_crs(epsg=4326)

    polygons = []
    for geometry in source.geometry:
        if geometry is not None and not geometry.is_empty:
            polygons.extend(polygon_parts(make_valid(geometry)))

    if not polygons:
        raise ValueError("Nie znaleziono poprawnej geometrii poligonowej.")

    return unary_union(polygons)


def generate_grid(boundary, resolution):
    """Generuje komórki H3 i przycina je do granicy powiatu."""
    h3_shape = h3.geo_to_h3shape(mapping(boundary))

    # overlap obejmuje również komórki przecinające granicę powiatu.
    cell_ids = h3.h3shape_to_cells_experimental(
        h3_shape,
        resolution,
        contain="overlap",
    )

    records = []

    for cell_id in sorted(cell_ids):
        # H3 zwraca (latitude, longitude), a Shapely wymaga (x, y).
        coordinates = [
            (longitude, latitude)
            for latitude, longitude in h3.cell_to_boundary(cell_id)
        ]

        full_cell = Polygon(coordinates)
        clipped = make_valid(full_cell.intersection(boundary))
        parts = polygon_parts(clipped)

        if not parts:
            continue

        merged = unary_union(parts)
        clipped_polygon = MultiPolygon(polygon_parts(merged))

        if clipped_polygon.is_empty or clipped_polygon.area <= 0:
            continue

        records.append(
            {
                "h3_id": cell_id,
                "resolution": resolution,
                "geometry": clipped_polygon,
            }
        )

    if not records:
        raise ValueError(
            f"Nie wygenerowano komórek dla rozdzielczości {resolution}."
        )

    grid = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")

    # Powierzchnia przyciętej komórki w m² — układ metryczny Polski.
    grid["area_m2"] = grid.to_crs(epsg=4326).geometry.area

    if grid["h3_id"].duplicated().any():
        raise ValueError("Wygenerowano zduplikowane identyfikatory H3.")

    if not grid.geometry.is_valid.all():
        raise ValueError("Siatka zawiera niepoprawne geometrie.")

    return grid


def main():
    parser = argparse.ArgumentParser(
        description="Generowanie siatek H3 dla granicy powiatu."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/data/powiat.shp"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/output"),
    )
    parser.add_argument(
        "--resolutions",
        type=int,
        nargs="+",
        choices=range(0, 16),
        default=[7, 8, 9],
    )
    args = parser.parse_args()

    boundary = read_boundary(args.input)
    args.output.mkdir(parents=True, exist_ok=True)

    for resolution in sorted(set(args.resolutions)):
        grid = generate_grid(boundary, resolution)
        destination = args.output / f"h3_r{resolution}.geojson"
        temporary = args.output / f"h3_r{resolution}.tmp.geojson"

        # Zastąpienie wyniku następuje dopiero po poprawnym zapisie.
        grid.to_file(
            temporary,
            driver="GeoJSON",
            engine="pyogrio",
            index=False,
        )
        temporary.replace(destination)

        print(
            f"OK | rozdzielczość={resolution} "
            f"| komórki={len(grid)} "
            f"| powierzchnia={grid['area_m2'].sum() / 1_000_000:.3f} km² "
            f"| plik={destination}",
            flush=True,
        )


if __name__ == "__main__":
    main()