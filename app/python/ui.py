from ui_common import (
    IOP, SCHEMAS, WINDOW_SIZE, messagebox, normalized_weights, queue, read_result_layer, threading, tk
)
from ui_layout import LayoutMixin
from ui_dialogs import DialogsMixin
from map_view import MapMixin
from scenarios import ScenarioMixin

class Viewer(LayoutMixin, DialogsMixin, MapMixin, ScenarioMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BDOT • analiza przejezdności")
        self.geometry(WINDOW_SIZE)
        self.minsize(1050, 650)
        self.engine = None
        self.environment = ""
        self.layers = {}
        self.order = []                  # pierwsza warstwa rysowana na wierzchu
        self.active = None
        self.selected = None             # (identyfikator warstwy, pozycja rekordu)
        self.counter = 0
        self.logged = False
        self.busy = False
        self.alive = True
        self.mode = "inspect"
        self.measure = []
        self.point_target = None
        self.theme = "Jasny"
        self.coord_crs = "4326"
        self.show_legend = True
        self.events = queue.Queue()
        self.build_ui()
        self.apply_theme()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.finish_tool())
        self.after(100, self.poll)
        self.after(150, self.login_dialog)


    def guarded(self, function):
        try:
            function()
        except Exception as error:
            messagebox.showerror("BDOT", str(error), parent=self)


    def invoke(self, name):
        if not self.logged:
            return
        if self.busy:
            self.status.set("Poczekaj na zakończenie odczytu danych.")
            return
        self.guarded(getattr(self, name))


    def background(self, task, callback):
        self.busy = True
        for button in self.buttons:
            button.configure(state="disabled")
        def worker():
            try:
                self.events.put((callback, task(), None))
            except Exception as error:
                self.events.put((callback, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()


    def poll(self):
        if not self.alive:
            return
        try:
            callback, result, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for button in self.buttons:
                button.configure(state="normal")
            if error:
                self.status.set("Odczyt nie powiódł się.")
                messagebox.showerror("Odczyt danych", error)
            else:
                self.guarded(lambda: callback(result))
        self.after(100, self.poll)


    def add_layer(self, layer, draw=True):
        self.counter += 1
        key = f"layer_{self.counter}"
        self.layers[key] = layer
        if draw:
            self.order.insert(0, key)
        else:
            self.order.append(key)
        if layer.data is not None and IOP in layer.data:
            layer.weights = normalized_weights(layer.data)
            layer.original_weights = dict(layer.weights)
            layer.column = IOP
            layer.original_iop = layer.data[IOP].copy()
        self.rebuild_tree()
        if draw:
            self.active = key
            self.selected = None
            self.attributes.delete(*self.attributes.get_children())
            self.tree.selection_set(key)
            self.draw(fit=True)
        return key


    def select_layer(self, event=None):
        if not self.logged or self.busy:
            return
        items = self.tree.selection()
        if not items or items[0] not in self.layers:
            return
        if items[0] == self.active and self.layers[items[0]].data is not None:
            return
        self.finish_tool()
        self.active = items[0]
        self.selected = None
        self.attributes.delete(*self.attributes.get_children())
        layer = self.layers[self.active]
        if layer.data is not None:
            self.draw()
            return
        key, engine = self.active, self.engine
        schema, table, geometry = layer.source
        quote = engine.dialect.identifier_preparer.quote_identifier
        def task():
            return read_result_layer(engine, schema, table, geometry)
        def ready(frame):
            layer.data, layer.visible = frame, True
            layer.weights = dict(frame.attrs.get("weights", {}))
            layer.original_weights = dict(layer.weights)
            layer.run_id = frame.attrs.get("run_id", "")
            layer.environment = frame.attrs.get("environment", getattr(self,"environment",""))
            if IOP in frame:
                layer.column, layer.original_iop = IOP, frame[IOP].copy()
            self.active = key
            self.rebuild_tree()
            self.draw(fit=True)
            self.status.set(frame.attrs.get("metadata_warning") or f"Wczytano {schema}.{table}; wersja: {layer.run_id or 'starsza'}. ")
        self.status.set(f"Wczytywanie {schema}.{table}…")
        self.background(task, ready)


    def rebuild_tree(self):
        opened = {self.tree.item(i,"text"):self.tree.item(i,"open") for i in self.tree.get_children()}
        self.tree.delete(*self.tree.get_children())
        groups = list(dict.fromkeys([self.layers[k].group for k in self.order]+list(SCHEMAS)+["Pliki lokalne","Punkty użytkownika"]))
        for i, group in enumerate(groups):
            parent = f"group_{i}"
            self.tree.insert("", "end", iid=parent, text=group, open=opened.get(group,True))
            for key in self.order:
                layer = self.layers[key]
                if layer.group == group:
                    mark = "●" if layer.visible else "○"
                    suffix = " *" if layer.modified or layer.dirty else ""
                    self.tree.insert(parent, "end", iid=key, text=f"{mark} {layer.name}{suffix}",
                                     tags=("grid",) if layer.name == "siatka" else ())
        if self.active in self.layers:
            self.tree.focus(self.active)
            self.tree.selection_set(self.active)


    def current(self):
        if self.active not in self.layers or self.layers[self.active].data is None:
            raise ValueError("Najpierw wybierz i wczytaj warstwę.")
        return self.layers[self.active]


    def toggle_active(self):
        layer = self.current()
        layer.visible = not layer.visible
        self.rebuild_tree()
        self.draw(fit=layer.visible and not self.has_extent)


    def confirm_unsaved(self):
        if any(l.dirty or l.modified for l in self.layers.values()):
            return messagebox.askyesno("Niezapisane zmiany", "Odrzucić niezapisane punkty i zmiany wskaźnika w podglądzie?")
        return True


    def close(self):
        if self.busy:
            messagebox.showinfo("Odczyt danych", "Poczekaj na zakończenie odczytu.")
            return
        if not self.confirm_unsaved():
            return
        self.alive = False
        if self.engine:
            self.engine.dispose()
        self.destroy()



if __name__ == "__main__":
    Viewer().mainloop()
