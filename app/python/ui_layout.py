import tkinter as tk
from ui_config import FONT, SIDEBAR_WIDTH, THEMES
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from tkinter import ttk, messagebox

from ui_config import MENUS, TOP_TOOLS, MAP_TOOLS
from ui_widgets import icon

class LayoutMixin:
    def build_ui(self):
        self.status = tk.StringVar(value="Zaloguj się do aplikacji.")
        self.coordinates = tk.StringVar(value="Współrzędne: —")
        self.scale_text = tk.StringVar(value="Skala ≈ —")
        self.buttons, self.icon_buttons, self.dropmenus = [], [], []
        menu_bar = ttk.Frame(self, padding=(10, 6))
        menu_bar.pack(fill="x")
        for title, entries in MENUS.items():
            button=ttk.Menubutton(menu_bar,text=title,padding=(14,6))
            menu=tk.Menu(button,tearoff=False,font=FONT)
            for label,method in entries:
                menu.add_command(label=label,command=lambda m=method:self.invoke(m))
            button.configure(menu=menu)
            button.pack(side="left",padx=(0,6))
            self.buttons.append(button); self.dropmenus.append(menu)
        tools=ttk.Frame(self,padding=(10,0,10,6))
        tools.pack(fill="x")
        for label,method,picture in TOP_TOOLS:
            self.tool_button(tools,label,picture,lambda m=method:self.invoke(m)).pack(side="left",padx=2)
        ttk.Separator(tools,orient="vertical").pack(side="left",fill="y",padx=10)
        self.nav_buttons={}
        for label,method,picture in MAP_TOOLS:
            button=self.tool_button(tools,label,picture,lambda m=method:self.navigate(m))
            button.pack(side="left",padx=2)
            self.nav_buttons[method]=button
        footer=ttk.Frame(self,padding=(10,5))
        footer.pack(side="bottom",fill="x")
        ttk.Label(footer,textvariable=self.status,wraplength=900).pack(anchor="w")
        self.panes=panes=ttk.Panedwindow(self,orient="horizontal")
        panes.pack(fill="both",expand=True,padx=10,pady=(0,5))
        self.sidebar=side=ttk.Frame(panes,width=SIDEBAR_WIDTH)
        self.mapbox=mapbox=ttk.Frame(panes)
        panes.add(side,weight=0); panes.add(mapbox,weight=1)
        self.sidebar_width=SIDEBAR_WIDTH
        self.sidebar_heading=heading=ttk.Frame(side); heading.pack(fill="x",pady=4)
        ttk.Label(heading,text="WARSTWY").pack(side="left")
        self.sidebar_toggle=ttk.Button(self,text="◀ Warstwy",command=self.toggle_sidebar)
        self.sidebar_toggle.pack(in_=heading,side="right")
        self.active_layer_text=tk.StringVar(value="Wybrana warstwa: —")
        self.active_layer_label=ttk.Label(side,textvariable=self.active_layer_text,wraplength=300)
        self.active_layer_label.pack(fill="x",pady=(0,8))
        side.bind("<Configure>",lambda e:self.active_layer_label.configure(wraplength=max(80,e.width-12)))
        self.map_info=info=ttk.Frame(mapbox,padding=(4,6)); info.pack(fill="x")
        self.scale_label=ttk.Label(info,textvariable=self.scale_text,font=("Arial",10,"bold"))
        self.scale_label.pack(side="right",padx=(12,6))
        self.coordinate_label=ttk.Label(info,textvariable=self.coordinates,font=("Arial",10))
        self.coordinate_label.pack(side="right",padx=(6,0))
        self.tree = self.table(side, (), height=12, tree=True)
        self.tree.tag_configure("grid", font=("Arial", 10, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self.select_layer)
        self.tree.bind("<Double-1>", lambda e: self.invoke("toggle_active"))
        self.layer_bar=layer_bar=ttk.Frame(side,padding=(0,5))
        layer_bar.pack(fill="x")
        self.layer_buttons=[]
        for label,picture,action in (("Góra","up",-1),("Dół","down",1),("Widoczność","eye","show"),("Usuń","delete","remove")):
            button=self.tool_button(layer_bar,label,picture,lambda a=action:self.layer_action(a),small=True)
            button.configure(width=1)
            self.layer_buttons.append(button)
        self.layer_columns=0
        layer_bar.bind("<Configure>",self.resize_layer_buttons)
        ttk.Label(side, text="ATRYBUTY • kliknij obiekt na mapie").pack(anchor="w", pady=8)
        self.attributes = self.table(side, ("Atrybut", "Wartość"), height=13)
        self.figure = Figure(figsize=(9, 7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=mapbox)
        self.toolbar = NavigationToolbar2Tk(self.canvas, mapbox, pack_toolbar=False)
        # Zachowujemy mechanizm nawigacji Matplotlib, ale pokazujemy własne czytelne przyciski.
        # Wbudowany pasek nie jest umieszczany w oknie.
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self.map_click)
        self.canvas.mpl_connect("motion_notify_event", self.motion)
        self.canvas.mpl_connect("scroll_event", self.wheel)
        self.canvas.mpl_connect("draw_event", self.update_scale)
        self.ax = self.figure.add_axes((0.03, 0.08, 0.80, 0.85))
        self.canvas.mpl_connect("resize_event", self.layout_map)
        self.draw()


    def clear_selection(self):
        self.selected=None
        self.attributes.delete(*self.attributes.get_children())
        self.event_generate("<<FeatureSelected>>")
        self.draw()
        self.status.set("Wyczyszczono zaznaczenie obiektu.")

    def reset_measure(self, finish_tool=False):
        """Usuwa punkty pomiaru; opcjonalnie kończy aktywne narzędzie."""
        self.measure.clear()
        if finish_tool:
            self.finish_tool()
        self.draw()

    def clear_measure(self):
        self.reset_measure(finish_tool=self.mode == "measure")
        self.status.set("Wyczyszczono pomiar odległości.")

    def hide_all_layers(self):
        self.set_all_visible(False)

    def show_all_layers(self):
        self.set_all_visible(True)

    def set_all_visible(self, visible):
        if not self.logged or self.busy:
            return
        count=0
        for layer in self.layers.values():
            layer.visible=bool(visible and layer.data is not None)
            count+=int(layer.visible)
        if not visible:
            self.selected=None
            self.attributes.delete(*self.attributes.get_children())
            self.event_generate("<<FeatureSelected>>")
        self.rebuild_tree()
        self.draw(fit=visible and not self.has_extent)
        unloaded=sum(layer.data is None for layer in self.layers.values())
        self.status.set((f"Pokazano {count} wczytanych warstw. Niewczytanych: {unloaded}."
                         if visible else "Ukryto wszystkie warstwy."))

    def toggle_sidebar(self):
        if str(self.sidebar) in self.panes.panes():
            self.sidebar_width=max(160,self.panes.sashpos(0))
            self.sidebar_toggle.pack_forget()
            self.sidebar_toggle.pack(in_=self.map_info,side="left",before=self.scale_label)
            self.panes.forget(self.sidebar)
            self.sidebar_toggle.configure(text="▶ Warstwy")
        else:
            self.panes.insert(0,self.sidebar,weight=0)
            self.sidebar_toggle.pack_forget()
            self.sidebar_toggle.pack(in_=self.sidebar_heading,side="right")
            self.sidebar_toggle.configure(text="◀ Warstwy")
            self.after_idle(lambda:self.panes.sashpos(0,min(self.sidebar_width,max(160,self.panes.winfo_width()-580))))
        self.canvas.draw_idle()

    def resize_layer_buttons(self,event):
        columns=4 if event.width>=360 else 2 if event.width>=180 else 1
        if columns==self.layer_columns:
            return
        self.layer_columns=columns
        for column in range(4):
            self.layer_bar.columnconfigure(column,weight=1 if column<columns else 0,uniform="layers" if column<columns else "")
        for index,button in enumerate(self.layer_buttons):
            button.grid(row=index//columns,column=index%columns,sticky="ew",padx=1,pady=2)

    def table(self, parent, columns, height=10, tree=False):
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        widget = ttk.Treeview(box, columns=columns, show="tree" if tree else "headings", height=height, selectmode="browse")
        if tree:
            widget.column("#0", width=330, minwidth=70, stretch=True)
        for c in columns:
            widget.heading(c, text=c)
            widget.column(c, width=185, minwidth=50, stretch=True)
        sy = ttk.Scrollbar(box, command=widget.yview)
        sx = ttk.Scrollbar(box, orient="horizontal", command=widget.xview)
        widget.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        widget.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        return widget


    def modal(self, title, size="540x360"):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry(size)
        window.transient(self)
        window.configure(bg=THEMES[self.theme]["bg"])
        window.grab_set()
        body = ttk.Frame(window, padding=15)
        body.pack(fill="both", expand=True)
        return window, body


    def action(self, parent, title, function):
        ttk.Button(parent, text=title, command=lambda: self.guarded(function)).pack(fill="x", pady=4)


    def entry(self, parent, title, default="", choices=None, secret=False):
        ttk.Label(parent, text=title).pack(anchor="w", pady=(5, 0))
        var = tk.StringVar(value=str(default))
        widget = (ttk.Combobox(parent, textvariable=var, values=choices, state="readonly")
                  if choices is not None else ttk.Entry(parent, textvariable=var, show="*" if secret else ""))
        widget.pack(fill="x", pady=3)
        return var


    def tool_button(self,parent,label,picture,command,small=False):
        button=ttk.Button(parent,text=label,command=command,compound="left" if small else "top",
                          style="Mini.TButton" if small else "Tool.TButton")
        self.buttons.append(button)
        self.icon_buttons.append((button,picture,16 if small else 22))
        return button

    def navigate(self,method):
        if not self.logged or self.busy:
            return
        if method in ("pan","zoom"):
            self.mode="inspect"; self.point_target=None
        if method=="home" and self.has_extent:
            self.draw(fit=True)
        else:
            getattr(self.toolbar,method)()
        self.sync_navigation()

    def sync_navigation(self):
        mode=str(self.toolbar.mode)
        for name,button in self.nav_buttons.items():
            active=(name=="pan" and mode=="pan/zoom") or (name=="zoom" and mode=="zoom rect")
            button.configure(style="Active.Tool.TButton" if active else "Tool.TButton")

    def layer_action(self,action):
        if not self.logged or self.busy:
            return
        selected=self.tree.selection()
        if not selected:
            return
        key=selected[0]
        if key not in self.layers:
            if action not in (-1,1):
                return
            group=self.tree.item(key,"text")
            groups=list(dict.fromkeys(self.layers[k].group for k in self.order))
            if group not in groups:
                return
            index=groups.index(group); target=index+action
            if 0<=target<len(groups):
                groups[index],groups[target]=groups[target],groups[index]
                self.order=[k for g in groups for k in self.order if self.layers[k].group==g]
        else:
            layer=self.layers[key]
            if action in (-1,1):
                siblings=[k for k in self.order if self.layers[k].group==layer.group]
                index=siblings.index(key); target=index+action
                if 0<=target<len(siblings):
                    a,b=self.order.index(key),self.order.index(siblings[target])
                    self.order[a],self.order[b]=self.order[b],self.order[a]
            elif action=="show":
                if layer.data is None:
                    self.status.set("Najpierw wczytaj warstwę, wybierając ją w panelu."); return
                layer.visible=not layer.visible
            else:
                if (layer.dirty or layer.modified) and not messagebox.askyesno("Usuń warstwę","Odrzucić niezapisane zmiany tej warstwy?",parent=self):
                    return
                self.order.remove(key); del self.layers[key]
                if self.active==key: self.active=None
                if self.selected and self.selected[0]==key:
                    self.selected=None; self.attributes.delete(*self.attributes.get_children())
                if self.point_target==key: self.finish_tool()
        self.rebuild_tree(); self.draw()
        if key not in self.layers and action in (-1,1):
            for node in self.tree.get_children():
                if self.tree.item(node,"text")==group:
                    self.tree.selection_set(node); break

    def apply_theme(self):
        colors=THEMES[self.theme]
        self.configure(bg=colors["bg"])
        style=ttk.Style(self); style.theme_use("clam")
        style.configure(".",font=FONT,background=colors["bg"],foreground=colors["fg"])
        for name in ("TButton","TMenubutton","Tool.TButton","Mini.TButton"):
            style.configure(name,background=colors["button"],foreground=colors["fg"],padding=6,font=FONT)
            style.map(name,background=[("disabled",colors["bg"]),("pressed",colors["active"]),("active",colors["active"])],
                      foreground=[("disabled",colors["muted"]),("active",colors["fg"])])
        style.configure("Tool.TButton",font=("Arial",9),padding=(10,5))
        style.configure("Mini.TButton",font=("Arial",9),padding=(3,5))
        style.configure("Active.Tool.TButton",background=colors["active"],foreground=colors["fg"])
        style.map("Active.Tool.TButton",foreground=[("active",colors["fg"]),("disabled",colors["muted"])])
        style.configure("Treeview",background=colors["panel"],fieldbackground=colors["panel"],foreground=colors["fg"],rowheight=25)
        for name in ("TCheckbutton","TRadiobutton"):
            style.configure(name,background=colors["bg"],foreground=colors["fg"],indicatorbackground=colors["panel"],indicatorforeground=colors["fg"])
            style.map(name,background=[("active",colors["button"])],foreground=[("disabled",colors["muted"]),("active",colors["fg"])],
                      indicatorbackground=[("selected",colors["select"]),("!selected",colors["panel"])])
        style.configure("TScrollbar",background=colors["button"],troughcolor=colors["panel"],arrowcolor=colors["fg"])
        style.configure("TScale",background=colors["button"],troughcolor=colors["panel"])
        style.map("Treeview.Heading",background=[("active",colors["active"])],foreground=[("active",colors["fg"])])
        style.configure("Treeview.Heading",background=colors["button"],foreground=colors["fg"],font=("Arial",10,"bold"))
        style.map("Treeview",background=[("selected",colors["select"])],foreground=[("selected",colors["fg"])])
        for name in ("TEntry","TCombobox"):
            style.configure(name,fieldbackground=colors["panel"],foreground=colors["fg"],insertcolor=colors["fg"],arrowcolor=colors["fg"])
            style.map(name,fieldbackground=[("readonly",colors["panel"])],foreground=[("readonly",colors["fg"])])
        self.option_add("*TCombobox*Listbox.background",colors["panel"])
        self.option_add("*TCombobox*Listbox.foreground",colors["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground",colors["select"])
        self.option_add("*TCombobox*Listbox.selectForeground",colors["fg"])
        style.map("TEntry",foreground=[("disabled",colors["muted"])])
        for menu in self.dropmenus:
            menu.configure(background=colors["panel"],foreground=colors["fg"],activebackground=colors["select"],activeforeground=colors["fg"])
        for button,picture,size in self.icon_buttons:
            button.icon=icon(self,picture,colors["fg"],size)
            button.configure(image=button.icon)
        self.sync_navigation()
        self.canvas.get_tk_widget().configure(background=colors["map"])
        def native(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Toplevel): child.configure(background=colors["bg"])
                elif isinstance(child,tk.Scale): child.configure(background=colors["panel"],foreground=colors["fg"],troughcolor=colors["button"],activebackground=colors["active"])
                elif isinstance(child,tk.Canvas) and child is not self.canvas.get_tk_widget(): child.configure(background=colors["panel"])
                native(child)
        native(self)
