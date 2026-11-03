import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import geopandas as gpd
import pandas as pd
from sqlalchemy import URL, create_engine, text
from shapely.geometry import Point

from matplotlib.figure import Figure
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)


SCHEMAS = ("results_r7", "results_r8", "results_r9")
ENVIRONMENTS = ("env-test-js-db", "env-qa-jo-db", "main")
IOP = "wsp_iop_norm"

COLORS = LinearSegmentedColormap.from_list(
    "przejezdnosc",
    ["#d7191c", "#ffffff", "#1a9641"],
    N=257,
)
SCALE = Normalize(vmin=-1, vmax=1)


def connection_from_docker(branch):
    """Odczytuje konfigurację bazy uruchomionej przez runnera."""
    if branch not in ENVIRONMENTS:
        raise ValueError("Nieznane środowisko.")

    project = f"remote-db-{branch}"

    def docker(*arguments):
        try:
            result = subprocess.run(
                ["docker", *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Nie znaleziono polecenia docker. Sprawdź instalację "
                "Docker Desktop i uruchom ponownie terminal lub PyCharm."
            ) from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Docker nie odpowiedział w ciągu 20 sekund."
            ) from None

        if result.returncode:
            raise RuntimeError(
                "Nie udało się odczytać Dockera. "
                "Sprawdź, czy Docker Desktop działa."
            )
        return result.stdout

    containers = docker(
        "ps", "-q",
        "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=postgis",
    ).split()

    if len(containers) != 1:
        raise RuntimeError(
            f"Oczekiwano jednej uruchomionej bazy dla {branch}; "
            f"znaleziono: {len(containers)}."
        )

    container = json.loads(docker("inspect", containers[0]))[0]

    environment = dict(
        item.split("=", 1)
        for item in container["Config"].get("Env", [])
        if "=" in item
    )

    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise RuntimeError(
            "Brak konfiguracji kontenera: " + ", ".join(missing)
        )

    bindings = container["NetworkSettings"]["Ports"].get("5432/tcp")
    if not bindings:
        raise RuntimeError(
            "Kontener nie udostępnia portu PostgreSQL na komputerze."
        )

    binding = next(
        (
            item for item in bindings
            if item["HostIp"] in ("127.0.0.1", "0.0.0.0", "")
        ),
        bindings[0],
    )

    host = binding["HostIp"]
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"

    return URL.create(
        "postgresql+psycopg2",
        username=environment["POSTGRES_USER"],
        password=environment["POSTGRES_PASSWORD"],
        host=host,
        port=int(binding["HostPort"]),
        database=environment["POSTGRES_DB"],
    )


class Viewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BDOT — wyniki agregacji")
        self.geometry("1400x900")
        self.minsize(1000, 650)

        self.engine = None
        self.data = None
        self.ax = None
        self.layer_nodes = {}
        self.events = queue.Queue()
        self.busy = False

        self.protocol("WM_DELETE_WINDOW", self.close)

        connection = ttk.LabelFrame(self, text="Połączenie z PostGIS")
        connection.pack(fill="x", padx=10, pady=8)

        ttk.Label(connection, text="Środowisko").grid(
            row=0, column=0, padx=5, sticky="w"
        )

        self.environment = ttk.Combobox(
            connection,
            values=ENVIRONMENTS,
            state="readonly",
            width=25,
        )
        self.environment.set("env-test-js-db")
        self.environment.grid(row=1, column=0, padx=5, pady=6)

        self.connect_button = ttk.Button(
            connection,
            text="Połącz / odśwież",
            command=self.connect,
        )
        self.connect_button.grid(row=1, column=1, padx=10)

        ttk.Label(
            connection,
            text="Dane połączenia pobierane automatycznie z Dockera",
        ).grid(row=1, column=2, padx=10)

        panels = ttk.Panedwindow(self, orient="horizontal")
        panels.pack(fill="both", expand=True, padx=10)

        left = ttk.Frame(panels, width=400)
        right = ttk.Frame(panels)
        panels.add(left, weight=1)
        panels.add(right, weight=3)

        ttk.Label(left, text="Warstwy wynikowe").pack(anchor="w")

        layers_frame = ttk.Frame(left)
        layers_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            layers_frame, show="tree", height=15, selectmode="browse"
        )
        self.tree.column("#0", width=350)
        self.tree.tag_configure(
            "grid",
            foreground="#175c35",
            font=("Segoe UI", 10, "bold"),
        )
        self.tree.bind("<<TreeviewSelect>>", self.select_layer)

        layers_scroll = ttk.Scrollbar(
            layers_frame, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=layers_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        layers_scroll.pack(side="right", fill="y")

        ttk.Label(
            left, text="Atrybuty klikniętego obiektu"
        ).pack(anchor="w", pady=(10, 3))

        attributes_frame = ttk.Frame(left)
        attributes_frame.pack(fill="both", expand=True)
        attributes_frame.rowconfigure(0, weight=1)
        attributes_frame.columnconfigure(0, weight=1)

        self.attributes = ttk.Treeview(
            attributes_frame,
            columns=("field", "value"),
            show="headings",
            height=14,
        )
        self.attributes.heading("field", text="Atrybut")
        self.attributes.heading("value", text="Wartość")
        self.attributes.column("field", width=260, stretch=False)
        self.attributes.column("value", width=160, stretch=False)

        attributes_y = ttk.Scrollbar(
            attributes_frame, command=self.attributes.yview
        )
        attributes_x = ttk.Scrollbar(
            attributes_frame,
            orient="horizontal",
            command=self.attributes.xview,
        )
        self.attributes.configure(
            yscrollcommand=attributes_y.set,
            xscrollcommand=attributes_x.set,
        )

        self.attributes.grid(row=0, column=0, sticky="nsew")
        attributes_y.grid(row=0, column=1, sticky="ns")
        attributes_x.grid(row=1, column=0, sticky="ew")

        self.figure = Figure(figsize=(8, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        self.toolbar = NavigationToolbar2Tk(
            self.canvas, right, pack_toolbar=False
        )
        self.toolbar.pack(fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self.pick)

        self.status = tk.StringVar(
            value="Wybierz środowisko i kliknij Połącz."
        )
        ttk.Label(
            self, textvariable=self.status, wraplength=1300
        ).pack(fill="x", padx=10, pady=8)

        self.after(100, self.poll)

    def background(self, task, callback):
        """Wykonuje odczyt poza wątkiem interfejsu."""
        if self.busy:
            return

        self.busy = True
        self.connect_button.configure(state="disabled")
        self.environment.configure(state="disabled")

        def worker():
            try:
                self.events.put((callback, task(), None))
            except Exception as error:
                self.events.put((callback, None, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.connect_button.configure(state="normal")
            self.environment.configure(state="readonly")

            if error:
                self.status.set("Błąd odczytu.")
                messagebox.showerror("Odczyt danych", error)
            else:
                try:
                    callback(result)
                except Exception:
                    self.status.set("Nie udało się wyświetlić warstwy.")
                    messagebox.showerror(
                        "Widok",
                        "Nie udało się wyświetlić warstwy. "
                        "Sprawdź jej geometrię i kolumny.",
                    )

        self.after(100, self.poll)

    def connect(self):
        if self.busy:
            return

        branch = self.environment.get()

        self.data = None
        self.ax = None
        self.layer_nodes.clear()
        self.tree.delete(*self.tree.get_children())
        self.attributes.delete(*self.attributes.get_children())
        self.figure.clear()
        self.canvas.draw_idle()

        if self.engine is not None:
            self.engine.dispose()
            self.engine = None

        def task():
            url = connection_from_docker(branch)

            engine = create_engine(
                url,
                connect_args={
                    "connect_timeout": 8,
                    "options": (
                        "-c default_transaction_read_only=on "
                        "-c statement_timeout=120000"
                    ),
                },
            )

            try:
                with engine.connect() as connection:
                    rows = connection.execute(text("""
                        SELECT
                            f_table_schema,
                            f_table_name,
                            f_geometry_column
                        FROM geometry_columns
                        WHERE f_table_schema IN (
                            'results_r7', 'results_r8', 'results_r9'
                        )
                        ORDER BY
                            f_table_schema,
                            (f_table_name = 'siatka') DESC,
                            f_table_name
                    """)).fetchall()
            except Exception:
                engine.dispose()
                raise RuntimeError(
                    "Odczytano konfigurację kontenera, ale połączenie "
                    "z PostgreSQL nie powiodło się. Sprawdź gotowość bazy "
                    "i zgodność jej danych logowania."
                ) from None

            return engine, rows, branch

        def connected(payload):
            self.engine, rows, connected_branch = payload
            self.show_layers(rows)
            self.title(
                f"BDOT — wyniki agregacji — {connected_branch}"
            )

        self.status.set(
            f"Odczytywanie konfiguracji i wyników: {branch}…"
        )
        self.background(task, connected)

    def show_layers(self, rows):
        groups = {
            schema: self.tree.insert(
                "", "end", text=schema, open=True
            )
            for schema in SCHEMAS
        }

        for schema, table, geometry in rows:
            is_grid = table == "siatka"
            label = (
                "SIATKA — parametry i wsp_iop_norm"
                if is_grid else table
            )
            node = self.tree.insert(
                groups[schema],
                "end",
                text=label,
                tags=("grid",) if is_grid else (),
            )
            self.layer_nodes[node] = (schema, table, geometry)

        self.status.set(
            f"Znaleziono {len(rows)} warstw. "
            "Wybierz siatkę lub warstwę wynikową."
        )

    def select_layer(self, _event=None):
        if self.busy or self.engine is None:
            return

        selected = self.tree.selection()
        if not selected or selected[0] not in self.layer_nodes:
            return

        schema, table, geometry = self.layer_nodes[selected[0]]
        if schema not in SCHEMAS:
            return

        engine = self.engine
        quote = engine.dialect.identifier_preparer.quote_identifier
        query = f"SELECT * FROM {quote(schema)}.{quote(table)}"

        def task():
            try:
                with engine.connect() as connection:
                    frame = gpd.read_postgis(
                        text(query),
                        connection,
                        geom_col=geometry,
                    )
            except Exception:
                raise RuntimeError(
                    f"Nie udało się odczytać {schema}.{table}. "
                    "Sprawdź, czy baza działa i import wyników zakończył się."
                ) from None

            # Układ metryczny na potrzeby mapy i tolerancji kliknięcia.
            if frame.crs is not None:
                frame = frame.to_crs(2180)
            elif frame.geometry.notna().any():
                raise ValueError(
                    f"Warstwa {schema}.{table} nie ma określonego CRS."
                )

            # Przygotowanie indeksu przestrzennego poza wątkiem UI.
            if not frame.empty:
                _ = frame.sindex

            return schema, table, frame

        self.status.set(f"Wczytywanie {schema}.{table}…")
        self.background(task, self.draw_layer)

    def draw_layer(self, payload):
        schema, table, frame = payload
        self.data = frame
        self.attributes.delete(*self.attributes.get_children())

        self.figure.clear()
        self.ax = self.figure.add_subplot(111)

        visible = frame[
            frame.geometry.notna() & ~frame.geometry.is_empty
        ]

        note = ""
        if not visible.empty:
            if table == "siatka" and IOP in visible.columns:
                values = pd.to_numeric(
                    visible[IOP], errors="coerce"
                )
                valid = values.notna() & values.between(-1, 1)

                # Szary podkład: brak IOP lub wartość poza zakresem.
                visible.plot(
                    ax=self.ax,
                    color="#bdbdbd",
                    edgecolor="#666666",
                    linewidth=0.15,
                )

                if valid.any():
                    colored = visible.loc[valid].copy()
                    colored[IOP] = values.loc[valid]
                    colored.plot(
                        ax=self.ax,
                        column=IOP,
                        cmap=COLORS,
                        norm=SCALE,
                        edgecolor="#666666",
                        linewidth=0.15,
                    )

                self.figure.colorbar(
                    ScalarMappable(norm=SCALE, cmap=COLORS),
                    ax=self.ax,
                    label=IOP,
                    ticks=[-1, -0.5, 0, 0.5, 1],
                    shrink=0.8,
                )

                note = (
                    f" | Szare oczka — brak IOP lub poza zakresem: "
                    f"{int((~valid).sum())}"
                )
            else:
                visible.plot(
                    ax=self.ax,
                    color="#5594bc",
                    linewidth=0.6,
                )
                if table == "siatka":
                    note = " | Brak kolumny wsp_iop_norm"
        else:
            note = " | Brak geometrii do wyświetlenia"

        self.ax.set_title(f"{schema}.{table}")
        self.ax.set_aspect("equal")
        self.ax.set_axis_off()

        self.figure.tight_layout()
        self.toolbar.update()
        self.canvas.draw_idle()

        self.status.set(
            f"{len(frame)} rekordów. "
            "Kliknij obiekt, aby odczytać atrybuty."
            + note
        )

    def pick(self, event):
        if (
            self.busy
            or self.data is None
            or self.data.empty
            or self.ax is None
            or event.inaxes is not self.ax
            or event.xdata is None
            or event.ydata is None
            or event.button != 1
            or self.toolbar.mode
        ):
            return

        point = Point(event.xdata, event.ydata)
        matches = self.data.sindex.query(
            point, predicate="intersects"
        )

        # Tolerancja dla punktów i linii: około 5 pikseli.
        if len(matches) == 0:
            width = abs(
                self.ax.get_xlim()[1] - self.ax.get_xlim()[0]
            )
            tolerance = width * 5 / max(self.ax.bbox.width, 1)
            matches = self.data.sindex.query(
                point.buffer(tolerance),
                predicate="intersects",
            )

        self.attributes.delete(*self.attributes.get_children())
        if len(matches) == 0:
            return

        index = min(
            matches,
            key=lambda i: (
                self.data.geometry.iloc[int(i)].distance(point),
                int(i),
            ),
        )
        row = self.data.iloc[int(index)]

        for name, value in row.items():
            if name == self.data.geometry.name:
                continue

            if value is None:
                display = "NULL"
            elif isinstance(value, (list, dict, tuple)):
                display = str(value)
            elif pd.isna(value):
                display = "NULL"
            elif isinstance(value, float):
                display = f"{value:.6f}"
            else:
                display = str(value)

            self.attributes.insert(
                "", "end", values=(name, display)
            )

    def close(self):
        if self.engine is not None:
            self.engine.dispose()
        self.destroy()


if __name__ == "__main__":
    Viewer().mainloop()