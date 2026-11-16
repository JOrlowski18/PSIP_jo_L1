import os
import uuid
from analysis import normalized_weights
from storage import save, save_analysis_metadata
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
from sqlalchemy import URL, create_engine, text

from h3_generator import (
    aggregate_grid,
    generate_grid,
    read_bdot,
    read_boundary,
)


def get_bdot(folder):
    """Lokalne GPKG albo pobranie paczki hajnowskiej na runnerze."""
    folder = Path(folder)
    if any(folder.rglob("*.gpkg")):
        return read_bdot(folder)

    url = (
        "https://opendata.geoportal.gov.pl/"
        "bdot10k/schemat2021/GPKG/20/2005_GPKG.zip"
    )

    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary)
        archive = target / "bdot.zip"
        print("Pobieranie BDOT10K powiatu hajnowskiego...", flush=True)

        with urllib.request.urlopen(url, timeout=120) as response:
            with archive.open("wb") as output:
                shutil.copyfileobj(response, output)

        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                name = Path(item.filename).name
                if item.is_dir() or not name.lower().endswith(".gpkg"):
                    continue
                with package.open(item) as source:
                    with (target / name).open("xb") as output:
                        shutil.copyfileobj(source, output)

        return read_bdot(target)


def main():
    run_id = uuid.uuid4().hex
    stage = os.getenv("ENVIRONMENT", "local")
    if stage not in {"local", "env-test-js-db", "env-qa-jo-db", "main"}:
        raise ValueError(f"Nieznane środowisko: {stage}")

    password = os.getenv("PGPASSWORD")
    if not password:
        raise ValueError("Brak PGPASSWORD.")

    resolutions = sorted({
        int(value.strip())
        for value in os.getenv("H3_RESOLUTIONS", "7,8,9").split(",")
        if value.strip()
    })
    if not resolutions or any(r < 0 or r > 15 for r in resolutions):
        raise ValueError("Rozdzielczości muszą być w zakresie 0–15.")

    boundary = read_boundary("/data/powiat.shp")
    grids = {
        resolution: generate_grid(boundary, resolution)
        for resolution in resolutions
    }
    layers = get_bdot(os.getenv("BDOT_DIR", "/data/bdot"))

    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            host=os.getenv("PGHOST", "postgis"),
            port=int(os.getenv("PGPORT", "5432")),
            username=os.getenv("PGUSER", "psip"),
            password=password,
            database=os.getenv("PGDATABASE", "psip"),
        ),
        connect_args={"connect_timeout": 15},
        pool_pre_ping=True,
    )

    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '30s'"))

            for schema in ("grid", "bdot"):
                connection.execute(text(
                    f"CREATE SCHEMA IF NOT EXISTS {schema}"
                ))

            county = gpd.GeoDataFrame(
                {"id": [1], "geom": [boundary]},
                geometry="geom",
                crs=4326,
            ).to_crs(2180)

            save(connection, county, "public", "powiat", "id")

            for code, layer in layers.items():
                source = layer["data"].copy()
                source["bdot_code"] = code
                save(
                    connection, source,
                    "bdot", layer["name"], "source_id",
                )

        # Osobna transakcja dla każdej rozdzielczości.
        for resolution, grid in grids.items():
            schema = f"results_r{resolution}"
            print(f"START: {schema}", flush=True)

            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '30s'"))
                connection.execute(text(
                    f"CREATE SCHEMA IF NOT EXISTS {schema}"
                ))

                save(
                    connection, grid,
                    "grid", f"h3_r{resolution}", "h3_id",
                )

                def save_class(name, frame):
                    save(connection, frame, schema, name, "h3_id")

                result, _ = aggregate_grid(grid, layers, on_class=save_class)

                save(
                    connection, result,
                    schema, "siatka", "h3_id",
                )
                save_analysis_metadata(
                    connection, schema, result, normalized_weights(result), run_id, stage,
                )

            print(f"ZATWIERDZONO: {schema}", flush=True)

        print("OK: zakończono cały import.", flush=True)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()