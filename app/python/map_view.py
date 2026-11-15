from ui_common import (
    GEOD, IOP, LinearSegmentedColormap, MAP_CRS, Normalize, Patch, Point, ScalarMappable, THEMES, TO_WEB, TO_WGS, gpd, math, messagebox, np, pd, shown
)
from matplotlib.colors import TwoSlopeNorm
from textwrap import fill

MAP_PADDING = 5  # margines pola nawigacji w pikselach
LEGEND_WIDTH = 250

def layer_norm(layer):
    if layer.column == IOP:
        if not layer.low < 0 < layer.high:
            raise ValueError("Zakres IOP musi obejmować zero: minimum < 0 < maksimum.")
        return TwoSlopeNorm(vmin=layer.low, vcenter=0, vmax=layer.high)
    return Normalize(layer.low,layer.high,clip=True)


class MapMixin:
    def draw(self, fit=False):
        colors = THEMES[self.theme]
        self.figure.set_facecolor(colors['map'])
        self.ax.set_facecolor(colors['map'])
        previous = getattr(self,'has_extent',False)
        limits = self.ax.get_xlim(), self.ax.get_ylim()
        if not hasattr(self,'artists'):
            self.artists = {}
            self.overlay = []
            self.scalebar = None
            self.legend_panel = self.figure.add_axes((.8,.01,.19,.98), facecolor='white', zorder=.5)
            self.legend_panel.set_xticks([]); self.legend_panel.set_yticks([])
            for spine in self.legend_panel.spines.values():
                spine.set_color('black'); spine.set_linewidth(1)
            self.legend_panel.text(.5,.97,'LEGENDA',ha='center',va='top',
                                   fontsize=12,fontweight='bold',color='black',transform=self.legend_panel.transAxes)
            self.cax = self.figure.add_axes((.87,.75,.10,.025), zorder=1)
            self.legend_ax = self.figure.add_axes((.85,.10,.14,.55), zorder=1)
            self.legend_ax.set_axis_off()
        for key in list(self.artists):
            if key not in self.layers:
                for artist, _ in self.artists.pop(key)[1]:
                    artist.remove()
        extents, handles, thematic = [], [], None
        for z,key in enumerate(reversed(self.order),1):
            layer = self.layers[key]
            frame = layer.data
            signature = (id(frame),len(frame)) if frame is not None else None
            cached = self.artists.get(key)
            if cached and cached[0] != signature:
                for artist,_ in cached[1]:
                    artist.remove()
                del self.artists[key]
                cached = None
            if frame is None or not layer.visible:
                if cached:
                    for artist,_ in cached[1]:
                        artist.set_visible(False)
                continue
            if cached is None:
                valid = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
                valid['_row_position'] = valid.index
                exploded = valid.explode(index_parts=False).reset_index(drop=True)
                items = []
                for kind,part in exploded.groupby(exploded.geom_type):
                    if kind not in ('Polygon','LineString','Point'):
                        continue
                    before = len(self.ax.collections)
                    part.plot(ax=self.ax,color=layer.color,linewidth=.25,markersize=28,aspect=None)
                    collections = list(self.ax.collections)[before:]
                    for artist in collections:
                        items.append((artist,part['_row_position'].to_numpy(dtype=int)))
                cached = (signature,items,valid.total_bounds if not valid.empty else None)
                self.artists[key] = cached
            if cached[2] is not None:
                extents.append(cached[2])
            for artist,indices in cached[1]:
                artist.set_visible(True)
                artist.set_zorder(z)
                artist.set_alpha(layer.alpha)
                if layer.column and layer.column in frame:
                    values = pd.to_numeric(frame.iloc[indices][layer.column],errors='coerce').to_numpy(float)
                    cmap = LinearSegmentedColormap.from_list('layer',layer.colors,N=257)
                    cmap = cmap.with_extremes(bad='#aaaaaa')
                    artist.set_color(cmap(layer_norm(layer)(np.ma.masked_invalid(values))))
                else:
                    artist.set_color(layer.color)
            if layer.column and (thematic is None or key==self.active):
                thematic=layer
            handles.append(Patch(facecolor=layer.colors[0] if layer.column else layer.color,label=fill(f'{layer.group}/{layer.name}', 27)))
        self.has_extent=bool(extents)
        if extents and (fit or not previous):
            bounds=np.array(extents)
            self.set_bounds((bounds[:,0].min(),bounds[:,1].min(),bounds[:,2].max(),bounds[:,3].max()))
        elif previous:
            self.ax.set_xlim(limits[0]); self.ax.set_ylim(limits[1])
        else:
            self.ax.set_xlim(0,1000); self.ax.set_ylim(0,1000)
        self.ax.set_aspect('equal',adjustable='datalim')
        self.ax.set_axis_off()
        self.ax.set_title('')
        layer = self.layers.get(self.active)
        self.active_layer_text.set(f"Wybrana warstwa: {layer.group}/{layer.name}" if layer else "Wybrana warstwa: —")
        legend=self.ax.get_legend()
        if legend:
            legend.remove()
        self.legend_ax.clear()
        self.legend_ax.set_axis_off()
        self.cax.clear()
        self.cax.set_visible(bool(self.show_legend and thematic))
        if self.show_legend and handles:
            self.legend_ax.legend(handles=handles[::-1],loc='upper left',borderaxespad=0,fontsize=9.1,frameon=False,labelcolor='black')
            if thematic:
                cmap=LinearSegmentedColormap.from_list('legend',thematic.colors,N=257)
                bar=self.figure.colorbar(ScalarMappable(norm=layer_norm(thematic),cmap=cmap),cax=self.cax,orientation='vertical',extend='neither')
                bar.set_label(thematic.column,color='black',fontsize=11,labelpad=10)
                bar.ax.tick_params(colors='black',labelsize=11)
                bar.outline.set_edgecolor('black')
        self.legend_ax.set_visible(bool(self.show_legend and handles))
        self.legend_panel.set_visible(self.legend_ax.get_visible())
        self.layout_map()
        for artist in self.overlay:
            artist.remove()
        self.overlay=[]
        before=len(self.ax.collections)
        if self.selected and self.selected[0] in self.layers:
            key,index=self.selected
            layer=self.layers[key]
            if layer.visible and layer.data is not None and index<len(layer.data):
                geom=layer.data.geometry.iloc[index]
                if geom is not None and not geom.is_empty:
                    shape=gpd.GeoSeries([geom],crs=MAP_CRS)
                    if 'Polygon' in geom.geom_type:
                        shape=shape.boundary
                    shape.plot(ax=self.ax,color='#ffb000',linewidth=2,markersize=80,zorder=20000,aspect=None)
        self.overlay.extend(list(self.ax.collections)[before:])
        if self.measure:
            xs,ys=zip(*self.measure)
            self.overlay.extend(self.ax.plot(xs,ys,'o--',color='#f0a000',zorder=20001))
        if fit or (self.has_extent and not previous):
            self.toolbar.push_current()
        self.canvas.draw_idle()

    def layout_map(self, event=None):
        """Stały margines w pikselach; legenda poza obszarem nawigacji."""
        width, height = self.figure.bbox.width, self.figure.bbox.height
        pad = min(MAP_PADDING, width*.12, height*.18)
        legends = hasattr(self, 'legend_ax') and self.legend_ax.get_visible()
        reserve = min(LEGEND_WIDTH, width*.32) if legends else 0
        self.ax.set_position((pad/width, pad/height,
                              max(1,width-2*pad-reserve)/width,
                              max(1,height-2*pad)/height))
        if hasattr(self, 'cax'):
            panel_left = width-pad-reserve+8
            self.legend_panel.set_position((panel_left/width,pad/height,
                                            max(1,reserve-8)/width,(height-2*pad)/height))
            left = (panel_left+24)/width
            bar_height = min(220, max(40, (height-2*pad)*.40))
            bar_top = height-pad-58
            self.cax.set_position((left, (bar_top-bar_height)/height,
                                   18/width, bar_height/height))
            top = bar_top-bar_height-30 if self.cax.get_visible() else height-pad-55
            self.legend_ax.set_position(((panel_left+12)/width,(pad+12)/height,
                                         max(20,reserve-32)/width,max(1,top-pad-12)/height))
        if event is not None:
            self.canvas.draw_idle()

    def set_bounds(self, bounds):
        x1, y1, x2, y2 = bounds
        if not np.isfinite(bounds).all():
            raise ValueError("Obiekt nie ma poprawnego zasięgu.")
        pad = max(x2 - x1, y2 - y1, 100) * 0.08
        self.ax.set_xlim(x1 - pad, x2 + pad)
        self.ax.set_ylim(y1 - pad, y2 + pad)


    def select_feature(self, key, index, zoom=False):
        self.active, self.selected = key, (key, int(index))
        layer = self.layers[key]
        row = layer.data.iloc[int(index)]
        self.attributes.delete(*self.attributes.get_children())
        for column, value in row.items():
            if column != layer.data.geometry.name:
                self.attributes.insert("", "end", values=(column, shown(value)))
        if zoom:
            geom = row[layer.data.geometry.name]
            if geom is None or geom.is_empty:
                raise ValueError("Wybrany rekord nie ma geometrii.")
            layer.visible = True
            self.set_bounds(geom.bounds)
            self.has_extent = True
        self.event_generate("<<FeatureSelected>>")
        self.draw()
        self.status.set(f"{layer.name} • rekord {int(index) + 1} / {len(layer.data)}")


    def map_click(self, event):
        if not self.logged or self.busy or event.inaxes is not self.ax or event.xdata is None or self.toolbar.mode:
            return
        if event.button != 1:
            return
        point = Point(event.xdata, event.ydata)
        if self.mode == "measure":
            self.measure.append((point.x, point.y))
            if len(self.measure) == 2:
                a, b = [TO_WEB.transform(*p) for p in self.measure]
                distance = math.hypot(b[0]-a[0], b[1]-a[1])
                self.mode = "inspect"
                self.draw()
                self.status.set(f"Odległość: {distance:,.2f} m")
                messagebox.showinfo("Odległość między punktami", f"{distance:,.2f} m\nOdległość płaska w EPSG:3857 (Web Mercator).")
            else:
                self.draw()
                self.status.set("Wskaż drugi punkt pomiaru. Esc — anuluj.")
            return
        if self.mode == "points":
            layer = self.layers.get(self.point_target)
            if layer is None:
                return self.finish_tool()
            extra = gpd.GeoDataFrame({"id": [len(layer.data) + 1], "name": [f"P{len(layer.data) + 1}"]}, geometry=[point], crs=MAP_CRS)
            layer.data = gpd.GeoDataFrame(pd.concat([layer.data, extra], ignore_index=True), crs=MAP_CRS)
            layer.dirty = True
            self.rebuild_tree()
            self.draw()
            self.status.set(f"Dodano punkt {len(layer.data)}. Esc — zakończ rysowanie.")
            return
        candidates = [self.active] if self.active in self.layers and self.layers[self.active].visible else self.order
        for key in candidates:
            layer = self.layers[key]
            if not layer.visible or layer.data is None or layer.data.empty:
                continue
            tolerance = abs(np.diff(self.ax.get_xlim())[0]) * 5 / max(self.ax.bbox.width, 1)
            matches = layer.data.sindex.query(point, predicate="intersects")
            if not len(matches):
                matches = layer.data.sindex.query(point.buffer(tolerance), predicate="intersects")
            if len(matches):
                index = min(matches, key=lambda i: (layer.data.geometry.iloc[int(i)].distance(point), int(i)))
                self.guarded(lambda: self.select_feature(key, index))
                return


    def motion(self,event):
        if event.inaxes is self.ax and event.xdata is not None and event.ydata is not None:
            lon,lat=TO_WGS.transform(event.xdata,event.ydata)
            self.coordinates.set(f"{abs(lat):.6f}°{'N' if lat>=0 else 'S'}, {abs(lon):.6f}°{'E' if lon>=0 else 'W'}")

    def wheel(self, event):
        if not self.logged or self.busy or event.inaxes is not self.ax or event.xdata is None:
            return
        factor = 0.8 if event.button == "up" else 1.25
        for getter, setter, center in ((self.ax.get_xlim, self.ax.set_xlim, event.xdata), (self.ax.get_ylim, self.ax.set_ylim, event.ydata)):
            a, b = getter()
            setter(center + (a - center) * factor, center + (b - center) * factor)
        self.canvas.draw_idle()


    def update_scale(self,event=None):
        if not self.has_extent:
            self.scale_text.set("Skala ≈ —"); return
        xmin,xmax=self.ax.get_xlim(); y=sum(self.ax.get_ylim())/2
        a,b=TO_WGS.transform(xmin,y),TO_WGS.transform(xmax,y)
        metres=abs(GEOD.inv(*a,*b)[2])
        screen_metres=self.ax.bbox.width/max(self.winfo_fpixels("1i"),1)*.0254
        denominator=metres/max(screen_metres,1e-9)
        self.scale_text.set("Skala ≈ 1:"+f"{denominator:,.0f}".replace(","," "))

    def finish_tool(self):
        if hasattr(self,"toolbar"):
            mode=str(self.toolbar.mode)
            if mode=="pan/zoom": self.toolbar.pan()
            elif mode=="zoom rect": self.toolbar.zoom()
            self.sync_navigation()
        self.mode = "inspect"
        self.point_target = None
        if hasattr(self, "status"):
            self.status.set("Tryb wskazywania obiektów.")


