FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-gdal \
        gdal-bin \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        "h3>=4.2,<5" \
        "geopandas>=1.0,<2" \
        "shapely>=2.0,<3" \
        "pyogrio>=0.9,<1" \
        "pyproj>=3.6,<4" \
        "SQLAlchemy>=2.0,<3" \
        "GeoAlchemy2>=0.14,<1" \
        "psycopg2-binary>=2.9,<3"

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY app/python/ /app/python/

COPY data/powiat.shp data/powiat.shx data/powiat.dbf data/powiat.prj data/powiat.cpg /data/

ENV PYTHONUNBUFFERED=1

CMD ["python3", "/app/python/load.py"]