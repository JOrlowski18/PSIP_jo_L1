import json
from datetime import datetime, timezone
from sqlalchemy import text

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



def save_analysis_metadata(connection, schema, frame, weights, run_id, environment):
    """Written in the same transaction as the grid. Contains no credentials."""
    quote=connection.dialect.identifier_preparer.quote_identifier
    table=f'{quote(schema)}.analysis_metadata'
    connection.execute(text(f'CREATE TABLE IF NOT EXISTS {table} (id integer PRIMARY KEY CHECK (id=1), payload jsonb NOT NULL)'))
    payload=dict(version=1, run_id=run_id, environment=environment,
                 generated_at=datetime.now(timezone.utc).isoformat(),
                 formula='sum(norm * weight) / count(weight != 0)',
                 normalized_weights=weights, cells=len(frame))
    connection.execute(text(f'INSERT INTO {table} (id,payload) VALUES (1,CAST(:payload AS jsonb)) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload'),
                       {'payload':json.dumps(payload)})
