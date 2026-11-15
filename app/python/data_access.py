import json
import subprocess
from pathlib import Path
import geopandas as gpd
from sqlalchemy import URL, text
from analysis import normalized_weights
from ui_config import ENVIRONMENTS, MAP_CRS, IOP, SCHEMAS

def docker_url(branch):
    if branch not in ENVIRONMENTS:
        raise ValueError("Nieznane środowisko.")

    def docker(*args):
        try:
            result = subprocess.run(
                ["docker", *args], capture_output=True, text=True,
                encoding="utf-8", timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("Nie można uruchomić Dockera. Sprawdź Docker Desktop.") from None
        if result.returncode:
            raise RuntimeError("Docker nie odpowiedział poprawnie. Sprawdź kontenery.")
        return result.stdout

    if branch == "local":
        compose=Path(__file__).resolve().parents[2]/"docker-compose-local.yaml"
        ids=docker("compose","-f",str(compose),"ps","-q","postgis").split()
    else:
        ids = docker("ps", "-q", "--filter", f"label=com.docker.compose.project=remote-db-{branch}",
                     "--filter", "label=com.docker.compose.service=postgis").split()
    if len(ids) != 1:
        raise ValueError(f"Środowisko {branch}: znaleziono {len(ids)} uruchomionych baz zamiast jednej.")
    info = json.loads(docker("inspect", ids[0]))[0]
    env = dict(s.split("=", 1) for s in info["Config"].get("Env", []) if "=" in s)
    if any(not env.get(k) for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")):
        raise ValueError("Niekompletne dane logowania w konfiguracji kontenera.")
    ports = info["NetworkSettings"]["Ports"].get("5432/tcp")
    if not ports:
        raise ValueError("Port bazy nie jest udostępniony w Windows.")
    port = next((p for p in ports if p["HostIp"] in ("", "0.0.0.0", "127.0.0.1")), ports[0])
    host = {"": "127.0.0.1", "0.0.0.0": "127.0.0.1", "::": "::1"}.get(port["HostIp"], port["HostIp"])
    return URL.create("postgresql+psycopg2", username=env["POSTGRES_USER"],
                      password=env["POSTGRES_PASSWORD"], host=host,
                      port=int(port["HostPort"]), database=env["POSTGRES_DB"])


def prepare(frame):
    if frame.crs is None:
        if frame.geometry.notna().any():
            raise ValueError("Brak CRS. Dla SHP sprawdź plik .prj.")
        frame = frame.set_crs(MAP_CRS)
    frame = frame.to_crs(MAP_CRS).reset_index(drop=True)
    _ = frame.sindex
    return frame



def read_result_layer(engine, schema, table, geometry):
    if schema not in SCHEMAS:
        raise ValueError('Dozwolone są tylko schematy wynikowe.')
    quote=engine.dialect.identifier_preparer.quote_identifier
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            frame=gpd.read_postgis(text(f'SELECT * FROM {quote(schema)}.{quote(table)}'),conn,geom_col=geometry)
            metadata=None
            exists=conn.execute(text('SELECT to_regclass(:table)'),{'table':f'{schema}.analysis_metadata'}).scalar()
            if exists:
                metadata=conn.execute(text(f'SELECT payload FROM {quote(schema)}.analysis_metadata WHERE id=1')).scalar()
    frame=prepare(frame)
    if metadata:
        frame.attrs['run_id']=metadata['run_id']
        frame.attrs['environment']=metadata['environment']
    if IOP in frame:
        if metadata:
            weights=metadata['normalized_weights']
            expected={c for c in frame.columns if c.endswith(('_area_m2_norm','_length_m_norm','_count_norm'))}
            if set(weights)!=expected:
                raise ValueError('Metadane wag nie odpowiadają kolumnom siatki. Uruchom import ponownie.')
            frame.attrs['weights']=weights
        else:
            frame.attrs['weights']=normalized_weights(frame)
            frame.attrs['metadata_warning']='Starszy wynik bez metadanych: suwaki używają lokalnego słownika. Zapisany IOP nie został zmieniony.'
    return frame
