"""Portable view/scenario settings; no database credentials or geometry copies."""
import json
import math
import numpy as np
from ui_config import IOP, THEMES
from pathlib import Path
from analysis import calculate_iop
from tkinter import filedialog, ttk

class ScenarioMixin:
    def scenario_dialog(self):
        window,body=self.modal('Scenariusz wag i wyglądu','500x300')
        ttk.Label(body,text='Zapis ustawień wczytanych warstw. Punkty zapisuj osobno jako SHP.',wraplength=440).pack(pady=10)
        def save():
            filename=filedialog.asksaveasfilename(parent=window,defaultextension='.json',filetypes=[('Scenariusz','*.json')])
            if not filename:
                return
            layers=[]
            for key in self.order:
                layer=self.layers[key]
                if layer.data is None:
                    continue
                layers.append(dict(name=layer.name,group=layer.group,visible=layer.visible,column=layer.column,
                                   low=layer.low,high=layer.high,colors=layer.colors,color=layer.color,
                                   alpha=layer.alpha,weights=layer.weights,source=layer.source,run_id=layer.run_id,environment=layer.environment))
            state=dict(version=2,layers=layers,theme=self.theme,xlim=self.ax.get_xlim(),ylim=self.ax.get_ylim())
            Path(filename).write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            self.status.set('Zapisano scenariusz. Dane źródłowe i punkty nie są częścią pliku.')
        def restore():
            filename=filedialog.askopenfilename(parent=window,filetypes=[('Scenariusz','*.json')])
            if not filename:
                return
            state=json.loads(Path(filename).read_text(encoding='utf-8'))
            if state.get('version')!=2:
                raise ValueError('Nieznana wersja scenariusza.')
            # Validate all changes before applying any of them.
            pending=[]
            for item in state['layers']:
                matches=[k for k in self.order if (self.layers[k].group,self.layers[k].name)==(item['group'],item['name'])]
                if len(matches)!=1:
                    raise ValueError(f"Wczytaj jednoznaczną warstwę {item['group']}/{item['name']}.")
                key=matches[0]; layer=self.layers[key]
                source=list(layer.source) if isinstance(layer.source,tuple) else layer.source
                if item.get('source')!=source or item.get('run_id','')!=layer.run_id or item.get('environment','')!=layer.environment:
                    raise ValueError('Scenariusz dotyczy innego źródła, środowiska lub wersji wyników.')
                if layer.data is None:
                    raise ValueError(f'Najpierw wczytaj warstwę {layer.name}.')
                if item['column'] and item['column'] not in layer.data:
                    raise ValueError('Brak atrybutu ze scenariusza.')
                if not math.isfinite(item['low']+item['high']) or item['low']>=item['high']:
                    raise ValueError('Niepoprawny zakres stylu.')
                if item['column']==IOP and not item['low']<0<item['high']:
                    raise ValueError('Zakres IOP musi obejmować zero.')
                if not 0<=item['alpha']<=1:
                    raise ValueError('Niepoprawna przezroczystość.')
                for color in list(item['colors'])+[item['color']]:
                    self.winfo_rgb(color)
                result=calculate_iop(layer.data,item['weights']) if item['weights'] else None
                pending.append((key,layer,item,result))
            if state['theme'] not in THEMES:
                raise ValueError('Nieznany motyw.')
            for axis in ('xlim','ylim'):
                bounds=state[axis]
                if len(bounds)!=2 or not np.isfinite(bounds).all() or bounds[0]>=bounds[1]:
                    raise ValueError('Niepoprawny zasięg mapy.')
            for key,layer,item,result in pending:
                for name in ('visible','column','low','high','colors','color','alpha','weights'):
                    setattr(layer,name,item[name])
                if result is not None:
                    layer.data[IOP]=result
                    layer.modified=True
            order=[key for key,_,_,_ in pending]
            self.order=order+[key for key in self.order if key not in order]
            self.theme=state['theme']; self.apply_theme()
            self.ax.set_xlim(state['xlim']); self.ax.set_ylim(state['ylim'])
            self.has_extent=True
            self.rebuild_tree(); self.draw()
            window.destroy()
        self.action(body,'Zapisz scenariusz',save)
        self.action(body,'Wczytaj scenariusz dla załadowanych warstw',restore)
