import os
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


def save(connection, frame, schema, table, key):
    quote = connection.dialect.identifier_preparer.quote
    qualified = f"{quote(schema)}.{quote(table)}"
    index_name = quote(f"idx_{table}_geom")

    if frame.empty or frame.geometry.isna().all():
        frame.drop(columns="geom").to_sql(
            table, connection, schema=schema,
            if_exists="replace", index=False,
        )
        connection.execute(text(
            f"ALTER TABLE {qualified} ADD COLUMN "
            f"geom geometry(Geometry,{frame.crs.to_epsg()})"
        ))
    else:
        frame.to_postgis(
            table, connection, schema=schema,
            if_exists="replace", index=False, chunksize=1000,
        )

    connection.execute(text(
        f"ALTER TABLE {qualified} ADD PRIMARY KEY ({quote(key)})"
    ))

    # GeoAlchemy zwykle tworzy już indeks o tej nazwie.
    connection.execute(text(
        f"CREATE INDEX IF NOT EXISTS {index_name} "
        f"ON {qualified} USING GIST (geom)"
    ))
    connection.execute(text(f"ANALYZE {qualified}"))

    count = connection.execute(
        text(f"SELECT COUNT(*) FROM {qualified}")
    ).scalar_one()

    if count != len(frame):
        raise RuntimeError(f"Niepełny zapis: {qualified}")

    print(f"Zapis: {schema}.{table}, wiersze: {count}", flush=True)


def main():
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
    layers = (
        get_bdot(os.getenv("BDOT_DIR", "/data/bdot"))
        if stage in {"local", "env-test-js-db"}
        else {}
    )

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

                if layers:
                    def save_class(name, frame):
                        save(
                            connection, frame,
                            schema, name, "h3_id",
                        )

                    result, _ = aggregate_grid(
                        grid, layers, on_class=save_class
                    )
                else:
                    result = grid.to_crs(4326)

                save(
                    connection, result,
                    schema, "siatka", "h3_id",
                )

            print(f"ZATWIERDZONO: {schema}", flush=True)

        print("OK: zakończono cały import.", flush=True)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()