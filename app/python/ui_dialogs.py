import geopandas as gpd
import math
import pandas as pd
import tkinter as tk
from ui_config import APP_LOGIN, APP_PASSWORD, CLASS_ORDER, ENVIRONMENTS, IOP, MAP_CRS, SCHEMAS, THEMES
from project_state import Layer
from pathlib import Path
from analysis import calculate_iop, normalized_weights
from tkinter import colorchooser, filedialog, messagebox, ttk
from sqlalchemy import create_engine, text
from data_access import docker_url, prepare
from ui_common import shown

class DialogsMixin:
    def login_dialog(self):
        window, body = self.modal("Logowanie do aplikacji", "400x280")
        user = self.entry(body, "Login")
        password = self.entry(body, "Hasło", secret=True)
        def submit():
            if user.get() != APP_LOGIN or password.get() != APP_PASSWORD:
                messagebox.showerror("Logowanie", "Nieprawidłowy login lub hasło.", parent=window)
                return
            password.set("")
            self.logged = True
            window.destroy()
            self.status.set("Zalogowano. Wczytaj SHP lub połącz się z PostgreSQL.")
        self.action(body, "Zaloguj", submit)
        window.bind("<Return>", lambda e: submit())
        window.protocol("WM_DELETE_WINDOW", self.close)


    def session_dialog(self):
        window, body = self.modal("Sesja aplikacji", "420x220")
        ttk.Label(body, text=f"Zalogowano jako: {APP_LOGIN}").pack(pady=15)
        def logout():
            if not self.confirm_unsaved():
                return
            self.finish_tool()
            for child in list(self.winfo_children()):
                if isinstance(child, tk.Toplevel) and child is not window:
                    child.destroy()
            if self.engine:
                self.engine.dispose()
            self.engine = None
            self.layers.clear()
            self.order.clear()
            self.active = self.selected = None
            self.logged = False
            self.measure.clear()
            self.rebuild_tree()
            self.attributes.delete(*self.attributes.get_children())
            self.draw()
            window.destroy()
            self.login_dialog()
        self.action(body, "Wyloguj", logout)


    def database_dialog(self):
        window, body = self.modal("Połączenie PostgreSQL", "500x270")
        branch = self.entry(body, "Środowisko", ENVIRONMENTS[0], ENVIRONMENTS)
        ttk.Label(body, text="Połączenie na podstawie konfiguracji lokalnego Dockera.", wraplength=450).pack(pady=10)
        def connect():
            selected_branch = branch.get()
            if any(l.modified and l.group in SCHEMAS for l in self.layers.values()):
                if not messagebox.askyesno("Wagi", "Odrzucić zmiany wag w podglądzie bazowym?", parent=window):
                    return
            window.destroy()
            def task():
                engine = create_engine(docker_url(selected_branch), connect_args={
                    "connect_timeout": 8,
                    "options": "-c default_transaction_read_only=on -c statement_timeout=120000",
                })
                try:
                    with engine.connect() as conn:
                        rows = conn.execute(text("""
                            SELECT f_table_schema, f_table_name, f_geometry_column
                            FROM geometry_columns
                            WHERE f_table_schema IN ('results_r7','results_r8','results_r9')
                            ORDER BY f_table_schema, (f_table_name='siatka') DESC, f_table_name
                        """)).fetchall()
                except Exception:
                    engine.dispose()
                    raise RuntimeError("Nie udało się połączyć z bazą. Sprawdź jej gotowość i dane logowania.") from None
                rows = sorted(rows, key=lambda row:(row[0], row[1]!="siatka", CLASS_ORDER.get(row[1],999), row[1]))
                return engine, rows
            def ready(payload):
                if self.engine:
                    self.engine.dispose()
                self.engine, rows = payload
                self.environment = selected_branch
                for child in list(self.winfo_children()):
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
                for key in list(self.order):
                    if self.layers[key].group in SCHEMAS:
                        self.order.remove(key)
                        del self.layers[key]
                self.active = self.selected = None
                self.measure.clear()
                for schema, table, geometry in rows:
                    self.add_layer(Layer(table, schema, source=(schema, table, geometry), environment=selected_branch), draw=False, refresh=False)
                self.rebuild_tree()
                self.draw()
                self.status.set(f"Połączono: {selected_branch}. Warstwy wynikowe: {len(rows)}.")
            self.status.set("Łączenie z bazą…")
            self.background(task, ready)
        self.action(body, "Połącz / odśwież", connect)


    def load_shp(self):
        filename = filedialog.askopenfilename(title="Wczytaj warstwę", filetypes=[("Shapefile", "*.shp")])
        if not filename:
            return
        path = Path(filename)
        def task():
            names = {p.name.lower() for p in path.parent.iterdir() if p.is_file()}
            missing = [s for s in (".shp", ".shx", ".dbf") if path.with_suffix(s).name.lower() not in names]
            if missing:
                raise ValueError("Brak plików składowych: " + ", ".join(missing))
            frame = prepare(gpd.read_file(path))
            if frame.empty:
                raise ValueError("Plik nie zawiera obiektów.")
            return frame
        self.status.set(f"Wczytywanie {path.name}…")
        self.background(task, lambda frame: self.add_layer(Layer(path.name, "Pliki lokalne", frame, source=str(path.resolve()), visible=True)))


    def weights_dialog(self):
        layer = self.current()
        weights = layer.weights or normalized_weights(layer.data)
        if not weights:
            raise ValueError("Warstwa nie ma kolumn agregacji zakończonych na _norm.")
        window, body = self.modal("Wagi klas i analiza oczka", "930x720")
        window.grab_release()
        target_key = self.active
        index = self.selected[1] if self.selected and self.selected[0] == target_key else None
        ttk.Label(body, text=f"{layer.group} / {layer.name}\nZmiany dotyczą podglądu całej siatki. Wagi zerowe nie liczą się do n.", wraplength=860).pack(anchor="w")
        summary = tk.StringVar()
        ttk.Label(body, textvariable=summary).pack(anchor="w", pady=8)
        area = ttk.Frame(body)
        area.pack(fill="both", expand=True)
        canvas = tk.Canvas(area, highlightthickness=0, bg=THEMES[self.theme]["panel"])
        scrollbar = ttk.Scrollbar(area, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows = ttk.Frame(canvas)
        frame_id = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(frame_id, width=e.width))
        sliders, labels = {}, {}
        def preview(*args):
            nonlocal index
            index = self.selected[1] if self.selected and self.selected[0] == target_key else None
            selected_weights = {c: v.get() for c, v in sliders.items()}
            active = sum(w != 0 for w in selected_weights.values())
            for column, var in sliders.items():
                value = float(layer.data.iloc[index][column]) if index is not None else None
                contribution = value * var.get() if value is not None else None
                labels[column].set(f"{var.get():+.2f} | norm={shown(value)} | wkład={shown(contribution)}")
            result = (
                calculate_iop(layer.data.iloc[[index]], selected_weights).iloc[0]
                if index is not None else None
            )
            summary.set(f"n={active}; wybrane oczko: {index + 1 if index is not None else 'brak — kliknij oczko na mapie'}; IOP={shown(result)}")
        for i, (column, weight) in enumerate(weights.items()):
            var = tk.DoubleVar(value=weight)
            sliders[column] = var
            labels[column] = tk.StringVar()
            ttk.Label(rows, text=column.removesuffix("_norm")).grid(row=i * 2, column=0, sticky="w", padx=5)
            slider = tk.Scale(rows, from_=-1, to=1, resolution=0.05, orient="horizontal", variable=var,
                              showvalue=False, length=290, command=preview,
                              bg=THEMES[self.theme]["panel"], fg=THEMES[self.theme]["fg"], highlightthickness=0)
            slider.grid(row=i * 2, column=1, sticky="ew")
            ttk.Label(rows, textvariable=labels[column]).grid(row=i * 2 + 1, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))
        rows.columnconfigure(1, weight=1)
        binding = self.bind("<<FeatureSelected>>", preview, add="+")
        window.bind("<Destroy>", lambda e: self.unbind("<<FeatureSelected>>",binding) if e.widget is window else None)
        preview()
        def apply():
            if self.layers.get(target_key) is not layer:
                raise ValueError("Warstwa została usunięta lub zmieniono bazę. Otwórz analizę ponownie.")
            selected_weights = {c: v.get() for c, v in sliders.items()}
            result = calculate_iop(layer.data, selected_weights)
            if layer.original_iop is None and IOP in layer.data:
                layer.original_iop = layer.data[IOP].copy()
            layer.data[IOP] = result
            layer.weights = selected_weights
            layer.column, layer.modified = IOP, True
            self.rebuild_tree()
            if index is not None:
                self.select_feature(target_key, index)
            else:
                self.draw()
            self.status.set("Przeliczono IOP w podglądzie. Baza PostgreSQL pozostaje bez zmian.")
        def reset():
            for column, value in (layer.original_weights or normalized_weights(layer.data)).items():
                sliders[column].set(value)
            preview()
        self.action(body, "Przelicz podgląd całej siatki", apply)
        self.action(body, "Przywróć wagi źródłowe", reset)
        if layer.original_iop is not None:
            def restore():
                layer.data[IOP] = layer.original_iop.copy()
                layer.weights = dict(layer.original_weights)
                layer.modified = False
                self.rebuild_tree()
                if index is not None:
                    self.select_feature(target_key, index)
                else:
                    self.draw()
                window.destroy()
            self.action(body, "Przywróć IOP odczytany ze źródła", restore)


    def style_dialog(self):
        layer = self.current()
        window, body = self.modal("Styl aktywnej warstwy", "540x610")
        numeric = [c for c in layer.data if pd.api.types.is_numeric_dtype(layer.data[c])]
        column = self.entry(body, "Atrybut (pusty = kolor jednolity)", layer.column, [""] + numeric)
        low = self.entry(body, "Minimum legendy", layer.low)
        high = self.entry(body, "Maksimum legendy", layer.high)
        opacity = tk.DoubleVar(value=layer.alpha)
        ttk.Label(body, text="Krycie").pack(anchor="w")
        ttk.Scale(body, from_=0.05, to=1, variable=opacity).pack(fill="x")
        colors = list(layer.colors)
        solid = [layer.color]
        def choose(target, index):
            color = colorchooser.askcolor(target[index], parent=window)[1]
            if color:
                target[index] = color
        for i, label in enumerate(("Kolor minimum", "Kolor środka", "Kolor maksimum")):
            self.action(body, label, lambda i=i: choose(colors, i))
        self.action(body, "Kolor jednolity", lambda: choose(solid, 0))
        ttk.Label(body, text="Zmiana stylu nie zmienia wskaźników. Dla IOP środkowy kolor odpowiada zeru; dla innych atrybutów połowie zakresu.", wraplength=480).pack(pady=8)
        def apply():
            a, b = float(low.get()), float(high.get())
            if not math.isfinite(a + b) or a >= b:
                raise ValueError("Podaj skończone minimum mniejsze od maksimum.")
            if column.get() == IOP and not a < 0 < b:
                raise ValueError("Dla IOP wymagane minimum < 0 < maksimum.")
            layer.column, layer.low, layer.high = column.get(), a, b
            layer.colors, layer.color, layer.alpha = tuple(colors), solid[0], opacity.get()
            self.draw()
            window.destroy()
        self.action(body, "Zastosuj styl", apply)


    def search_dialog(self):
        layer = self.current()
        key = self.active
        columns = [c for c in layer.data if c != layer.data.geometry.name]
        if not columns:
            raise ValueError("Warstwa nie ma atrybutów.")
        window, body = self.modal("Wyszukiwanie po atrybucie", "650x650")
        column = self.entry(body, "Atrybut", columns[0], columns)
        operator = self.entry(body, "Warunek", "zawiera", ("zawiera", "=", "!=", ">", ">=", "<", "<=", "NULL"))
        value = self.entry(body, "Wartość")
        result_text = tk.StringVar()
        ttk.Label(body, textvariable=result_text).pack()
        results = self.table(body, ("Rekord", "Wartość"), height=10)
        def search():
            series = layer.data[column.get()]
            op, raw = operator.get(), value.get()
            if op == "NULL":
                mask = series.isna()
            elif op == "zawiera":
                mask = series.astype("string").str.contains(raw, case=False, regex=False, na=False)
            else:
                if pd.api.types.is_bool_dtype(series):
                    if raw.lower() not in ("true","false","1","0"):
                        raise ValueError("Podaj true/false albo 1/0.")
                    target = raw.lower() in ("true","1")
                elif pd.api.types.is_numeric_dtype(series):
                    target = float(raw)
                elif pd.api.types.is_datetime64_any_dtype(series):
                    target = pd.Timestamp(raw)
                else:
                    series, target = series.astype("string"), raw
                mask = {"=": series.eq, "!=": series.ne, ">": series.gt, ">=": series.ge, "<": series.lt, "<=": series.le}[op](target).fillna(False) & series.notna()
            matches = layer.data.index[mask].tolist()
            results.delete(*results.get_children())
            for index in matches[:1000]:
                results.insert("", "end", iid=str(index), values=(index + 1, shown(layer.data.iloc[index][column.get()])))
            result_text.set(f"Znaleziono {len(matches)}. Lista pokazuje maksymalnie 1000 wyników.")
        def zoom():
            items = results.selection()
            if items:
                self.select_feature(key, int(items[0]), zoom=True)
        self.action(body, "Wyszukaj", search)
        self.action(body, "Pokaż atrybuty i przybliż wynik", zoom)


    def zoom_dialog(self):
        layer = self.current()
        window, body = self.modal("Przybliżenie", "430x250")
        def selected():
            if not self.selected or self.selected[0] != self.active:
                raise ValueError("Najpierw kliknij obiekt lub wybierz wynik wyszukiwania.")
            self.select_feature(*self.selected, zoom=True)
            window.destroy()
        def extent():
            visible = layer.data[layer.data.geometry.notna() & ~layer.data.geometry.is_empty]
            if visible.empty:
                raise ValueError("Warstwa nie ma geometrii.")
            layer.visible = True
            self.set_bounds(visible.total_bounds)
            self.has_extent = True
            self.draw()
            window.destroy()
        self.action(body, "Zoom do wybranego obiektu", selected)
        self.action(body, "Zoom do całej aktywnej warstwy", extent)


    def measure_dialog(self):
        window, body = self.modal("Pomiar odległości", "440x260")
        ttk.Label(body, text="Po uruchomieniu wskaż dwa punkty na mapie. Wynik w metrach układu EPSG:3857 (Web Mercator). Nie jest to odległość geodezyjna.", wraplength=390).pack(pady=10)
        def start():
            if not self.has_extent:
                raise ValueError("Najpierw wyświetl warstwę na mapie.")
            if self.toolbar.mode:
                raise ValueError("Wyłącz przesuwanie lub zoom na pasku mapy.")
            self.measure.clear()
            self.mode = "measure"
            window.destroy()
            self.status.set("Wskaż pierwszy punkt pomiaru. Esc — anuluj.")
        self.action(body, "Wskaż dwa punkty", start)
        self.action(body, "Usuń linię pomiaru", lambda: self.reset_measure(finish_tool=True))


    def points_dialog(self):
        window, body = self.modal("Warstwa punktowa", "500x440")
        name = self.entry(body, "Nazwa nowej warstwy", "Moje punkty")
        def create():
            if not name.get().strip():
                raise ValueError("Podaj nazwę warstwy.")
            frame = gpd.GeoDataFrame({"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="str")},
                                     geometry=gpd.GeoSeries([], crs=MAP_CRS), crs=MAP_CRS)
            self.add_layer(Layer(name.get().strip(), "Punkty użytkownika", frame, visible=True, editable=True))
        def start():
            layer = self.current()
            if not layer.editable:
                raise ValueError("Wybierz utworzoną warstwę punktową.")
            if not self.has_extent:
                raise ValueError("Najpierw wyświetl warstwę odniesienia, np. SHP lub siatkę.")
            if self.toolbar.mode:
                raise ValueError("Wyłącz przesuwanie lub zoom na pasku mapy.")
            self.mode, self.point_target = "points", self.active
            window.destroy()
            self.status.set("Klikaj mapę, aby dodawać punkty. Esc — zakończ.")
        def undo():
            layer = self.current()
            if not layer.editable:
                raise ValueError("Wybierz warstwę punktową użytkownika.")
            if not layer.data.empty:
                layer.data = layer.data.iloc[:-1].copy().reset_index(drop=True)
                layer.dirty = True
                self.selected = None
                self.draw()
        def save():
            layer = self.current()
            if not layer.editable or layer.data.empty:
                raise ValueError("Wybierz warstwę punktową zawierającą punkty.")
            filename = filedialog.asksaveasfilename(parent=window, title="Zapis punktów", defaultextension=".shp", filetypes=[("Shapefile", "*.shp")])
            if not filename:
                return
            path = Path(filename)
            siblings = [p for p in path.parent.iterdir() if p.stem.lower() == path.stem.lower() and p.suffix.lower() in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
            if siblings and not messagebox.askyesno("Zastąp pliki", "Zastąpić istniejący zestaw SHP o tej nazwie?", parent=window):
                return
            layer.data.to_crs(4326).to_file(path, driver="ESRI Shapefile", encoding="UTF-8", index=False)
            layer.dirty = False
            self.rebuild_tree()
            self.status.set(f"Zapisano punkty w EPSG:4326: {path}")
        for title, fn in (("Utwórz pustą warstwę", create), ("Dodawaj punkty kliknięciem", start),
                          ("Usuń ostatni punkt", undo), ("Zapisz aktywną warstwę jako SHP", save)):
            self.action(body, title, fn)


    def coordinates_dialog(self):
        window,body=self.modal("Współrzędne kursora","490x260")
        ttk.Label(body,text="Współrzędne są wyświetlane nad mapą, w prawym górnym rogu w stopniach dziesiętnych (EPSG:4326).\n\nKolejność: szerokość N/S, długość E/W.\nPrzykład: 52.771119°N, 18.321333°E",wraplength=430).pack(pady=12)
        self.action(body,"Zamknij",window.destroy)

    def legend_dialog(self):
        window, body = self.modal("Legenda", "470x250")
        enabled = tk.BooleanVar(value=self.show_legend)
        ttk.Checkbutton(body, text="Pokaż legendę i skalę barwną", variable=enabled).pack(pady=10)
        ttk.Label(body, text="Skala barw opisuje aktywną widoczną warstwę tematyczną; jeśli jej nie ma — inną widoczną warstwę tematyczną.", wraplength=420).pack()
        def apply():
            self.show_legend = enabled.get()
            self.draw()
            window.destroy()
        self.action(body, "Zastosuj", apply)


    def theme_dialog(self):
        window, body = self.modal("Wygląd aplikacji", "400x220")
        choice = self.entry(body, "Motyw", self.theme, tuple(THEMES))
        def apply():
            self.theme = choice.get()
            window.destroy()
            self.apply_theme()
            self.draw()
        self.action(body, "Zastosuj", apply)


    def pdf_dialog(self):
        if not self.has_extent:
            raise ValueError("Najpierw wyświetl dane na mapie.")
        window, body = self.modal("Eksport mapy do PDF", "500x300")
        title = self.entry(body, "Tytuł mapy", "Przejezdność terenu")
        ttk.Label(body, text="Eksport bieżącego zasięgu i widocznych warstw, z aktualnym stylem i legendą. Skala liczbowa znajduje się nad mapą, w prawym górnym rogu. Skala liczbowa ekranu nie określa skali wydruku.", wraplength=440).pack(pady=10)
        def export():
            filename = filedialog.asksaveasfilename(parent=window, defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
            if not filename:
                return
            self.canvas.draw()
            old = self.ax.get_title()
            try:
                self.ax.set_title(title.get(), color=THEMES[self.theme]["fg"])
                self.figure.savefig(filename, format="pdf", facecolor=self.figure.get_facecolor(),
                                    metadata={"Title": title.get(), "Creator": "BDOT Tkinter"})
            finally:
                self.ax.set_title(old)
                self.canvas.draw_idle()
            self.status.set(f"Zapisano mapę: {filename}")
            window.destroy()
        self.action(body, "Zapisz PDF", export)


