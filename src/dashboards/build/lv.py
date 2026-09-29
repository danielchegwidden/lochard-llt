"""Tiny builder for AI/BI (Lakeview) serialized dashboards.

Widget specs follow real exported .lvdash.json files (counter v2, table v2, filters v2, charts v3, combo v1,
pivot v3 multi-cell). Datasets use unqualified names – the bundle sets dataset_catalog / dataset_schema to the
target's lochard_semantic schema, so the same JSON deploys to dev and prod.
"""
from __future__ import annotations

import hashlib
import json

LOCHARD = {
    "orange": "#F47525", "crimson": "#A3194E", "grey": "#565150", "grey2": "#5F5856", "sky": "#52B2E5",
    "amber": "#FFC000", "sand": "#FFDF96", "brown": "#8E4737", "green": "#6BBF59", "red": "#D64545", "lgrey": "#BDBDBD",
    "purple": "#6A2C91", "pink": "#E8175D", "cyan": "#00AEEF", "dorange": "#ED6D05",
}
PALETTE = [LOCHARD[k] for k in ["orange", "sky", "crimson", "grey", "amber", "brown", "cyan", "purple", "lgrey"]]
LOGO = "https://www.lochardenergy.com.au/wp-content/uploads/2020/09/LE_Logo-reworked.svg"


def _id(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8]


def fmt_money(places=0, compact=True):
    return {"type": "number-currency", "currencyCode": "AUD", "abbreviation": "compact" if compact else "none",
            "decimalPlaces": {"type": "max", "places": places}}


def fmt_num(places=0, compact=False):
    return {"type": "number-plain", "abbreviation": "compact" if compact else "none",
            "decimalPlaces": {"type": "max", "places": places}}


def fmt_pct(places=1):
    return {"type": "number-percent", "decimalPlaces": {"type": "max", "places": places}}


class Field:
    """Aggregation field: name used by encodings, expression used by the query."""

    def __init__(self, name: str, expr: str, display: str | None = None, fmt: dict | None = None):
        self.name, self.expr, self.display, self.fmt = name, expr, display or name, fmt

    def q(self):
        return {"name": self.name, "expression": self.expr}


def col(c: str, display=None) -> Field:
    return Field(c, f"`{c}`", display or c)


def s(c: str, display=None, fmt=None) -> Field:
    return Field(f"sum({c})", f"SUM(`{c}`)", display or c, fmt)


def agg(name: str, expr: str, display=None, fmt=None) -> Field:
    return Field(name, expr, display or name, fmt)


class Page:
    def __init__(self, dash: "Dashboard", name: str, display: str, page_type: str = "PAGE_TYPE_CANVAS"):
        self.dash, self.name, self.display, self.page_type = dash, name, display, page_type
        self.layout, self.y, self.x, self.row_h = [], 0, 0, 0

    # ------------------------------------------------------------------ layout
    def _place(self, widget: dict, w: int, h: int):
        if self.x + w > 6:
            self.newline()
        self.layout.append({"widget": widget, "position": {"x": self.x, "y": self.y, "width": w, "height": h}})
        self.x += w
        self.row_h = max(self.row_h, h)
        if self.x >= 6:
            self.newline()

    def newline(self):
        if self.x:
            self.y += self.row_h
        self.x, self.row_h = 0, 0

    def _wname(self, *parts):
        return _id(self.name, len(self.layout), *parts)

    # ------------------------------------------------------------------ widgets
    def text(self, md: str, w=6, h=1):
        self._place({"name": self._wname("t", md[:20]), "multilineTextboxSpec": {"lines": [md]}}, w, h)

    def header(self, title: str, subtitle: str, right: str | None = None):
        self.text(f"![Lochard Energy]({LOGO})", w=1, h=2)
        self.text(f"## {title}\n\n{subtitle}", w=4 if right else 5, h=2)
        if right:
            self.text(right, w=1, h=2)

    def _query(self, ds: str, fields: list[Field], disagg=False, name="main_query"):
        return {"name": name, "query": {"datasetName": ds, "fields": [f.q() for f in fields], "disaggregated": disagg}}

    def counter(self, ds: str, value: Field, title: str, w=1, h=2, desc: str | None = None):
        enc = {"value": {"fieldName": value.name, "displayName": title, **({"format": value.fmt} if value.fmt else {})}}
        spec = {"version": 2, "widgetType": "counter", "encodings": enc, "frame": _frame(title, desc)}
        self._place({"name": self._wname("c", title), "queries": [self._query(ds, [value])], "spec": spec}, w, h)

    def chart(self, kind: str, ds: str, x: Field, ys: list[Field], title: str, w=3, h=6, color: Field | None = None,
              x_type="categorical", colors=None, labels=False, stacked=False, desc=None, y_title=None, x_title=None,
              color_map: dict | None = None, sort_x=None):
        fields = [x] + ys + ([color] if color else [])
        enc = {"x": {"fieldName": x.name, "scale": {"type": x_type, **({"sort": {"by": sort_x}} if sort_x else {})},
                     "displayName": x_title or x.display}}
        if len(ys) == 1:
            enc["y"] = {"fieldName": ys[0].name, "scale": {"type": "quantitative"}, "displayName": y_title or ys[0].display,
                        **({"format": ys[0].fmt} if ys[0].fmt else {})}
        else:
            enc["y"] = {"scale": {"type": "quantitative"}, "fields": [
                {"fieldName": f.name, "displayName": f.display, **({"format": f.fmt} if f.fmt else {})} for f in ys]}
        if color:
            sc = {"type": "categorical"}
            if color_map:
                sc["mappings"] = [{"value": k, "color": v} for k, v in color_map.items()]
            enc["color"] = {"fieldName": color.name, "scale": sc, "displayName": color.display}
        enc["label"] = {"show": labels}
        spec = {"version": 3, "widgetType": kind, "encodings": enc, "frame": _frame(title, desc),
                "mark": {"colors": colors or PALETTE,
                         **({"layout": "stack"} if stacked else {"layout": "group"} if kind == "bar" and len(ys) > 1 else {})}}
        self._place({"name": self._wname(kind, title), "queries": [self._query(ds, fields)], "spec": spec}, w, h)

    def pie(self, ds: str, value: Field, cat: Field, title: str, w=3, h=6, color_map: dict | None = None, desc=None):
        sc = {"type": "categorical"}
        if color_map:
            sc["mappings"] = [{"value": k, "color": v} for k, v in color_map.items()]
        enc = {"angle": {"fieldName": value.name, "scale": {"type": "quantitative"}, "displayName": value.display},
               "color": {"fieldName": cat.name, "scale": sc, "displayName": cat.display}, "label": {"show": True}}
        spec = {"version": 3, "widgetType": "pie", "encodings": enc, "frame": _frame(title, desc)}
        self._place({"name": self._wname("pie", title), "queries": [self._query(ds, [cat, value])], "spec": spec}, w, h)

    def combo(self, ds: str, x: Field, bars: list[Field], lines: list[Field], title: str, w=3, h=6,
              x_type="categorical", labels=False, desc=None, dual=False, grouped=False):
        """dual=True gives the line its own right-hand axis (each side carries its own scale, as the UI writes it)."""
        fl = lambda fs: [{"fieldName": f.name, "displayName": f.display, **({"format": f.fmt} if f.fmt else {})} for f in fs]
        q = {"type": "quantitative"}
        y = ({"primary": {"fields": fl(bars), "scale": q}, "secondary": {"fields": fl(lines), "scale": q}} if dual else
             {"primary": {"fields": fl(bars)}, "secondary": {"fields": fl(lines)}, "scale": q})
        enc = {"x": {"fieldName": x.name, "scale": {"type": x_type}, "displayName": x.display}, "y": y,
               "label": {"show": labels}}
        spec = {"version": 1, "widgetType": "combo", "encodings": enc, "frame": _frame(title, desc),
                **({"mark": {"layout": "group"}} if grouped else {})}
        self._place({"name": self._wname("combo", title), "queries": [self._query(ds, [x] + bars + lines)],
                     "spec": spec}, w, h)

    def pivot(self, ds: str, rows: list[Field], cells: list[Field], title: str, columns: list[Field] | None = None,
              w=6, h=8, desc=None, totals=True, heat=False):
        """Measures render as columns (displayAs=columns, like a PBI matrix); row groups get subtotals.
        heat=True applies a colour-scale background (PBI conditional-formatting heatmap)."""
        style = {"style": {"type": "color-scale", "backgroundColor": {"scale": {"type": "quantitative",
                 "colorRamp": {"mode": "scheme", "scheme": "orangered"}}}}} if heat else {}
        enc = {"rows": [{"fieldName": r.name, "displayName": r.display, **({"displayTotal": True} if totals else {})}
                        for r in rows],
               "columns": [{"fieldName": c.name, "displayName": c.display} for c in (columns or [])],
               "cell": {"type": "multi-cell", "displayAs": "columns",
                        "fields": [{"fieldName": c.name, "cellType": "text", "displayName": c.display,
                                    **({"format": c.fmt} if c.fmt else {}), **style} for c in cells]}}
        spec = {"version": 3, "widgetType": "pivot", "encodings": enc, "frame": _frame(title, desc)}
        self._place({"name": self._wname("pivot", title), "queries": [self._query(ds, rows + (columns or []) + cells)],
                     "spec": spec}, w, h)

    def table(self, ds: str, cols: list[tuple[str, str]], title: str, w=6, h=8, desc=None):
        fields = [col(c) for c, _ in cols]
        enc = {"columns": [{"fieldName": c, "displayName": d} for c, d in cols]}  # table spec v2: name + label only
        spec = {"version": 2, "widgetType": "table", "encodings": enc, "frame": _frame(title, desc)}
        self._place({"name": self._wname("tbl", title), "queries": [self._query(ds, fields, disagg=True)], "spec": spec},
                    w, h)

    def filter(self, kind: str, field: str, title: str, datasets: list[str], w=1, h=2, default=None, params=None):
        """kind: multi | single | date. default: list of values or (min, max) for date ranges."""
        wid = {"multi": "filter-multi-select", "single": "filter-single-select", "date": "filter-date-range-picker"}[kind]
        queries, enc = [], []
        for ds in datasets:
            qn = f"f_{self.name}_{ds}_{field}"
            queries.append({"name": qn, "query": {"datasetName": ds, "fields": [
                {"name": field, "expression": f"`{field}`"},
                {"name": f"{field}_associativity", "expression": "COUNT_IF(`associative_filter_predicate_group`)"}],
                "disaggregated": False}})
            enc.append({"fieldName": field, "displayName": title, "queryName": qn})
        for ds, p in (params or []):
            qn = f"p_{self.name}_{ds}_{p}"
            queries.append({"name": qn, "query": {"datasetName": ds, "parameters": [{"name": p, "keyword": p}],
                                                  "disaggregated": False}})
            enc.append({"parameterName": p, "queryName": qn})
        spec = {"version": 2, "widgetType": wid, "encodings": {"fields": enc}, "frame": {"showTitle": True, "title": title}}
        if default is not None:
            if kind == "date":
                spec["selection"] = {"defaultSelection": {"range": {"dataType": "DATE", "min": {"value": default[0]},
                                                                     "max": {"value": default[1]}}}}
            else:
                spec["selection"] = {"defaultSelection": {"values": {"dataType": "STRING",
                                                                     "values": [{"value": v} for v in default]}}}
        self._place({"name": self._wname("f", field), "queries": queries, "spec": spec}, w, h)


def _frame(title, desc=None):
    f = {"showTitle": True, "title": title}
    if desc:
        f.update(showDescription=True, description=desc)
    return f


class Dashboard:
    def __init__(self, name: str):
        self.name, self.datasets, self.pages = name, [], []

    def dataset(self, name: str, display: str, sql: str, parameters: list[dict] | None = None) -> str:
        ds = {"name": name, "displayName": display, "queryLines": [l + "\n" for l in sql.strip().splitlines()]}
        if parameters:
            ds["parameters"] = parameters
        self.datasets.append(ds)
        return name

    def page(self, name: str, display: str, page_type="PAGE_TYPE_CANVAS") -> Page:
        p = Page(self, name, display, page_type)
        self.pages.append(p)
        return p

    def to_dict(self):
        return {"datasets": self.datasets,
                "pages": [{"name": p.name, "displayName": p.display, "layout": p.layout, "pageType": p.page_type}
                          for p in self.pages],
                "uiSettings": {"theme": {
                    "canvasBackgroundColor": {"light": "#F4F4F4", "dark": "#1E1C1B"},
                    "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#2A2726"},
                    "widgetBorderColor": {"light": "#E6E1DF", "dark": "#3A3634"},
                    "fontColor": {"light": "#1E1E1E", "dark": "#F4F4F4"},
                    "selectionColor": {"light": LOCHARD["orange"], "dark": LOCHARD["orange"]},
                    "visualizationColors": PALETTE, "widgetHeaderAlignment": "LEFT"},
                    "genieSpace": {"isEnabled": True}}}

    def write(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
