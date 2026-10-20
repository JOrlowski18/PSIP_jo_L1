import os
import subprocess
from pathlib import Path

from sqlalchemy import URL, create_engine, text

from h3_generator import generate_grid, read_boundary


def main():
    shapefile = Path("/data/powiat.shp")

    if not shapefile.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {shapefile}")

    # Parametry połączenia z kontenerem PostgreSQL.
    environment = os.environ.copy()
    environment.setdefault("PGHOST", "postgis")
    environment.setdefault("PGPORT", "5432")
    environment.setdefault("PGDATABASE", "psip")
    environment.setdefault("PGUSER", "psip")
    environment.setdefault("PGPASSWORD", "psip")

    resolutions = sorted(
        {
            int(value.strip())
            for value in os.getenv("H3_RESOLUTIONS", "7,8,9").split(",")
            if value.strip()
        }
    )

    if not resolutions or any(r < 0 or r > 15 for r in resolutions):
        raise ValueError("Rozdzielczości H3 muszą mieścić się w zakresie 0–15.")

    # 1. Dotychczasowy import granicy powiatu.
    # Dane połączenia ogr2ogr odczytuje ze zmiennych PG*.
    command = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        "PG:",
        str(shapefile),
        "-nln", "public.powiat",
        "-lco", "GEOMETRY_NAME=geom",
        "-overwrite",
    ]

    subprocess.run(command, env=environment, check=True)
    print("Załadowano powiat.shp do tabeli public.powiat.", flush=True)

    # 2. Generowanie siatek w pamięci — bez zapisywania GeoJSON.
    boundary = read_boundary(shapefile)
    grids = {}

    for resolution in resolutions:
        print(
            f"Generowanie siatki H3 — rozdzielczość {resolution}...",
            flush=True,
        )

        grid = generate_grid(boundary, resolution)

        # Układ metryczny potrzebny do późniejszej agregacji BDOT10K.
        grid = grid.to_crs(epsg=2180).rename_geometry("geom")
        grid["area_m2"] = grid.geometry.area

        grids[resolution] = grid

    # 3. Połączenie do zapisu siatek.
    connection_url = URL.create(
        drivername="postgresql+psycopg2",
        username=environment["PGUSER"],
        password=environment["PGPASSWORD"],
        host=environment["PGHOST"],
        port=int(environment["PGPORT"]),
        database=environment["PGDATABASE"],
    )

    engine = create_engine(
        connection_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )

    counts = {}

    try:
        # Wszystkie siatki zapisujemy w jednej transakcji.
        with engine.begin() as connection:
            connection.execute(
                text("CREATE SCHEMA IF NOT EXISTS grid")
            )

            for resolution, grid in grids.items():
                table_name = f"h3_r{resolution}"

                grid.to_postgis(
                    name=table_name,
                    con=connection,
                    schema="grid",
                    if_exists="replace",
                    index=False,
                    chunksize=1000,
                )

                # Nazwa tabeli pochodzi ze zweryfikowanej liczby 0–15.
                connection.execute(
                    text(
                        f'ALTER TABLE grid."{table_name}" '
                        "ADD PRIMARY KEY (h3_id)"
                    )
                )

                count = connection.execute(
                    text(f'SELECT COUNT(*) FROM grid."{table_name}"')
                ).scalar_one()

                if count != len(grid):
                    raise RuntimeError(
                        f"Niepełny zapis {table_name}: {count}/{len(grid)}"
                    )

                counts[table_name] = count

        for table_name, count in counts.items():
            print(
                f"OK: grid.{table_name} — zapisano {count} komórek.",
                flush=True,
            )

        print("Import siatek do PostGIS zakończony.", flush=True)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()