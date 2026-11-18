"""
CAMELS-IND Explorer
A web app for browsing the CAMELS-IND dataset (472 catchments, Peninsular India, 1980-2020):
map of catchments, hydrographs, flow duration curves, seasonal patterns, catchment comparison
and attribute charts.

Run:   streamlit run app.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from plotly.subplots import make_subplots

import camels_loader as cl
from labels import nice

st.set_page_config(page_title="CAMELS-IND Explorer", page_icon="💧", layout="wide",
                   initial_sidebar_state="expanded")

CACHE_DIR = Path(os.environ.get("CAMELS_CACHE", Path.home() / ".camels_ind_cache"))

# ----------------------------------------------------------------------------- look and feel
# Colour-blind-safe categorical palette, always used in this fixed order.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OBS, MODEL, RAIN = PALETTE[0], PALETTE[1], "#8db9ea"
SEQ = [[0, "#dbe8f8"], [0.5, "#5a9be3"], [1, "#0b3d7a"]]          # one hue, light -> dark
INK, INK2, GRID = "#1f2328", "#5b6270", "#eceff3"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PLOT_CONFIG = {"displaylogo": False,
               "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
               "toImageButtonOptions": {"format": "png", "scale": 3, "filename": "camels-ind-chart"}}

pio.templates["camels"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, Segoe UI, Helvetica, Arial, sans-serif", size=13, color=INK),
    colorway=PALETTE, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white",
    xaxis=dict(gridcolor=GRID, linecolor="#c9ced6", showline=True, ticks="outside", tickcolor="#c9ced6",
               zeroline=False, title_font=dict(size=13, color=INK2)),
    yaxis=dict(gridcolor=GRID, linecolor="#c9ced6", showline=True, ticks="outside", tickcolor="#c9ced6",
               zeroline=False, title_font=dict(size=13, color=INK2)),
    hoverlabel=dict(bgcolor="white", bordercolor="#c9ced6", font=dict(size=13, color=INK)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12, color=INK2)),
    margin=dict(l=10, r=10, t=36, b=10), hovermode="closest",
))
pio.templates.default = "plotly_white+camels"

st.markdown("""
<style>
.block-container {padding-top: 3rem; padding-bottom: 2rem; max-width: 1500px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.hero {padding: 1.4rem 1.6rem; border-radius: 14px; margin-bottom: 1.2rem;
       background: linear-gradient(120deg, #0b3d7a 0%, #2a78d6 60%, #5ab0e8 100%); color: white;}
.hero h1 {color: white; margin: 0 0 .3rem 0; font-size: 2.0rem;}
.hero p {color: #e6f0fb; margin: 0; font-size: 1.02rem;}
.pagehead {margin: 0 0 .2rem 0; font-size: 1.6rem; font-weight: 700;}
.pagesub {color: #5b6270; margin: 0 0 1rem 0;}
div[data-testid="stMetric"] {background: #f6f8fb; border: 1px solid #e6e9ef; border-radius: 12px;
       padding: .7rem .9rem;}
div[data-testid="stMetricValue"] {font-size: 1.35rem; font-weight: 650;}
div[data-testid="stMetricLabel"] p {color: #5b6270;}
.note {color:#5b6270; font-size:.9rem;}
.card {border:1px solid #e6e9ef; border-radius:12px; padding:1rem 1.1rem; background:white; height:100%;}
.card b {font-size:1.02rem;}
</style>""", unsafe_allow_html=True)


def header(title, subtitle=""):
    st.markdown(f"<div class='pagehead'>{title}</div>" + (f"<div class='pagesub'>{subtitle}</div>" if subtitle else ""),
                unsafe_allow_html=True)


def show(fig, height=420, key=None, **kw):
    fig.update_layout(height=height)
    return st.plotly_chart(fig, width="stretch", theme=None, config=PLOT_CONFIG, key=key, **kw)


# ----------------------------------------------------------------------------- data
@st.cache_resource(show_spinner="Reading the CAMELS-IND files (first time only) ...")
def open_dataset(root: str) -> cl.CamelsData:
    data = cl.scan_folder(root)
    obs_kind = next((k for k in data.streamflow_files if "Observed" in k), None)
    if obs_kind:
        wide = cl.load_wide_table(str(data.streamflow_files[obs_kind]))
        avail = wide["df"].notna().mean() * 100
        avail.index = [cl.canonical_id(c) for c in avail.index]
        data.attributes["Observed flow available (%)"] = avail.reindex(data.attributes.index).round(1)
        data.attribute_groups["Observed flow available (%)"] = "Data availability"
    for k in data.streamflow_files:            # warm up the streamflow cache once
        cl.load_wide_table(str(data.streamflow_files[k]))
    return data


def default_folder():
    for cand in [os.environ.get("CAMELS_DIR"), "data", "CAMELS_IND", str(CACHE_DIR)]:
        if cand and Path(cand).exists() and any(Path(cand).rglob("*.csv")):
            return cand
    return None


def data_loader_panel(expanded):
    with st.expander("Load or change data", expanded=expanded, icon=":material/database:"):
        how = st.radio("Where is the data?", ["Download from Zenodo", "Folder on this computer", "Upload the zip"],
                       help="Zenodo is the official CAMELS-IND release (version 2.2). It downloads once, "
                            "then the app keeps a copy.")
        if how == "Download from Zenodo":
            choice = st.selectbox("Which part", list(cl.ZENODO_FILES))
            if st.button("Download and open", type="primary", icon=":material/download:"):
                bar = st.progress(0.0, text="Downloading ...")
                try:
                    folder = cl.download_from_zenodo(
                        cl.ZENODO_FILES[choice], CACHE_DIR,
                        progress=lambda f: bar.progress(min(f, 1.0), text=f"Downloading ... {f:.0%}"))
                    st.session_state.root = str(folder)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Download failed: {e}")
        elif how == "Folder on this computer":
            path = st.text_input("Folder path", value=st.session_state.get("root") or "",
                                 placeholder=r"D:\CAMELS_IND\CAMELS_IND_All_Catchments")
            if st.button("Open folder", type="primary", icon=":material/folder_open:"):
                if Path(path).exists():
                    st.session_state.root = path
                    st.rerun()
                else:
                    st.error("That folder does not exist.")
        else:
            up = st.file_uploader("CAMELS-IND zip file", type="zip")
            if up is not None and st.button("Open zip", type="primary"):
                with st.spinner("Unzipping ..."):
                    st.session_state.root = str(cl.extract_uploaded_zip(up.getvalue(), CACHE_DIR))
                st.rerun()


# ----------------------------------------------------------------------------- helpers
def numeric_attrs(data):
    return [c for c in data.attributes.columns
            if c != "Gauge ID" and pd.api.types.is_numeric_dtype(data.attributes[c])
            and data.attributes[c].notna().sum() > 2]


def text_attrs(data):
    return [c for c in data.attributes.columns
            if c != "Gauge ID" and not pd.api.types.is_numeric_dtype(data.attributes[c])
            and 1 < data.attributes[c].nunique() < 40]


def to_mm_per_day(q, area_km2):
    if q is None or area_km2 is None or not np.isfinite(area_km2) or area_km2 <= 0:
        return None
    return q * 86.4 / area_km2


@st.cache_data(show_spinner=False, max_entries=64)
def catchment_daily(root, cid, units):
    """Daily table (flows + rainfall) for one catchment; cached so repeat views are instant."""
    data = open_dataset(root)
    out = {}
    area = data.attributes.loc[cid, data.area_col] if data.area_col else np.nan
    for kind in data.streamflow_files:
        s = data.streamflow(cid, kind)
        if s is None or s.notna().sum() == 0:
            continue
        if units == "mm/day":
            s = to_mm_per_day(s, area)
            if s is None:
                continue
        out[kind] = s.astype("float64")
    f = data.forcing(cid)
    rc = data.rain_column(f) if f is not None else None
    if rc:
        out["Rainfall"] = f[rc]
    return pd.DataFrame(out).sort_index() if out else pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=64)
def catchment_forcing(root, cid):
    f = open_dataset(root).forcing(cid)
    return f if f is not None else pd.DataFrame()


def aggregate(df, step):
    if step == "Daily" or df.empty:
        return df
    rule = {"Monthly": "MS", "Yearly": "YS"}[step]
    out = df.resample(rule).mean()
    if "Rainfall" in df:
        out["Rainfall"] = df["Rainfall"].resample(rule).sum(min_count=1)
    return out


def flow_duration(s):
    v = np.sort(s.dropna().values)[::-1]
    if v.size == 0:
        return np.array([]), v
    exceed = np.arange(1, v.size + 1) / (v.size + 1) * 100
    if v.size > 3000:                                   # thin it out: same curve, far fewer points
        idx = np.unique(np.geomspace(1, v.size, 1500).astype(int) - 1)
        return exceed[idx], v[idx]
    return exceed, v


def line(x, y, name, color, width=2.0, gl=False, **kw):
    trace = go.Scattergl if gl else go.Scatter
    return trace(x=x, y=y, name=name, mode="lines", line=dict(color=color, width=width), **kw)


def fmt(v, digits=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
        return "–"
    if isinstance(v, (int, float, np.floating, np.integer)):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.{digits}f}"
    return str(v).title()


# ----------------------------------------------------------------------------- sidebar filters
def sidebar_filters(data):
    att = data.attributes
    keep = pd.Series(True, index=att.index)
    st.sidebar.markdown("**Filter catchments**")
    for col in [data.basin_col, data.state_col]:
        if col and att[col].notna().any():
            options = sorted(att[col].dropna().astype(str).unique())
            pick = st.sidebar.multiselect(nice(col), options, placeholder="All", key=f"f_{col}")
            if pick:
                keep &= att[col].astype(str).isin(pick)
    if "Observed flow available (%)" in att:
        min_av = st.sidebar.slider("Minimum observed flow data (%)", 0, 100, 0, 5, key="f_avail",
                                   help="Hide catchments with many gaps in observed streamflow.")
        if min_av:
            keep &= att["Observed flow available (%)"].fillna(0) >= min_av
    with st.sidebar.expander("Filter by any attribute"):
        num = numeric_attrs(data)
        col = st.selectbox("Attribute", ["None"] + num, format_func=lambda c: "None" if c == "None" else nice(c),
                           key="f_attr")
        if col != "None":
            lo, hi = float(np.nanmin(att[col])), float(np.nanmax(att[col]))
            if lo < hi:
                r = st.slider("Range", lo, hi, (lo, hi), key=f"f_rng_{col}")
                if r != (lo, hi):
                    keep &= att[col].between(*r)
    ids = list(att.index[keep])
    st.sidebar.caption(f"Showing **{len(ids)}** of {len(att)} catchments")
    return ids


def pick_catchment(data, ids):
    if not ids:
        st.warning("No catchments match the filters in the sidebar.")
        st.stop()
    current = st.session_state.get("cid")
    index = ids.index(current) if current in ids else 0
    cid = st.selectbox("Catchment", ids, index=index, format_func=data.label, key="cid_select",
                       help="Type a gauge ID, site or river name to search.")
    st.session_state.cid = cid
    return cid


# ----------------------------------------------------------------------------- map figure
def catchment_map(data, ids, color_by=None, size_by_area=False, highlight=None, height=600, zoom=4.3):
    att = data.attributes.loc[ids].dropna(subset=[data.lat_col, data.lon_col]).copy()
    att["Name"] = [data.label(i) for i in att.index]
    att["cid"] = att.index
    hover = {data.lat_col: ":.3f", data.lon_col: ":.3f", "cid": False}
    if data.area_col:
        hover[data.area_col] = ":,.0f"
    kw = dict(lat=data.lat_col, lon=data.lon_col, hover_name="Name", custom_data=["cid"], zoom=zoom,
              center=dict(lat=float(att[data.lat_col].mean()), lon=float(att[data.lon_col].mean())),
              map_style="carto-positron", labels={c: nice(c) for c in att.columns})
    if color_by:
        kw["color"] = color_by
        hover[color_by] = ":.3g" if pd.api.types.is_numeric_dtype(att[color_by]) else True
        if pd.api.types.is_numeric_dtype(att[color_by]):
            kw["color_continuous_scale"] = SEQ
        else:
            cats = att[color_by].astype(str).value_counts()
            keep = list(cats.index[:7])   # fixed palette: biggest 7 groups, the rest become "Other"
            att[color_by] = att[color_by].astype(str).where(att[color_by].astype(str).isin(keep), "Other")
            kw["color_discrete_sequence"] = PALETTE
            kw["category_orders"] = {color_by: keep + ["Other"]}
    if size_by_area and data.area_col:
        att["_size"] = np.sqrt(att[data.area_col].fillna(att[data.area_col].median()))
        kw["size"] = "_size"
        kw["size_max"] = 24
        hover["_size"] = False
    fig = px.scatter_map(att, hover_data=hover, **kw)
    if not size_by_area:
        fig.update_traces(marker=dict(size=10, opacity=0.9))
    if highlight and highlight in att.index:
        r = att.loc[highlight]
        fig.add_trace(go.Scattermap(lat=[r[data.lat_col]], lon=[r[data.lon_col]], mode="markers",
                                    marker=dict(size=20, color="#e34948", opacity=0.9), name="Selected",
                                    hovertext=[r["Name"]], hoverinfo="text"))
        outline = cl.catchment_outline(data, highlight)
        if outline:
            for k, (lons, lats) in enumerate(outline):
                fig.add_trace(go.Scattermap(lon=list(lons), lat=list(lats), mode="lines", fill="toself",
                                            fillcolor="rgba(42,120,214,0.12)", line=dict(color=OBS, width=2),
                                            name="Catchment boundary", showlegend=k == 0, hoverinfo="skip"))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=height,
                      legend=dict(bgcolor="rgba(255,255,255,0.85)", y=0.99, yanchor="top", x=0.01),
                      coloraxis_colorbar=dict(title=dict(text=nice(color_by) if color_by else "", side="right"),
                                              thickness=12, len=0.7))
    return fig


# ============================================================================= pages
def page_home():
    data = DATA
    att = data.attributes
    st.markdown("""<div class='hero'><h1>💧 CAMELS-IND Explorer</h1>
    <p>Daily streamflow, weather and catchment attributes for 472 river catchments in Peninsular India,
    1980–2020 — explore it without writing code.</p></div>""", unsafe_allow_html=True)

    m = st.columns(5)
    m[0].metric("Catchments", f"{len(att)}")
    if "Observed flow available (%)" in att:
        m[1].metric("With good observed flow (>30%)", f"{int((att['Observed flow available (%)'] > 30).sum())}")
    m[2].metric("Attributes per catchment", f"{len(numeric_attrs(data)) + len(text_attrs(data))}")
    m[3].metric("Weather variables", f"{len(catchment_forcing(ROOT, next(iter(data.forcing_files))).columns)}"
                if data.forcing_files else "–")
    if data.streamflow_files:
        df = cl.load_wide_table(str(next(iter(data.streamflow_files.values()))))["df"]
        m[4].metric("Period", f"{df.index.min().year}–{df.index.max().year}")

    left, right = st.columns([3, 2], gap="large")
    with left:
        if data.lat_col and data.lon_col:
            num = numeric_attrs(data)
            col = "p_mean" if "p_mean" in num else None
            show(catchment_map(data, list(att.index), color_by=col, height=470, zoom=4.0), 470, key="home_map")
            st.caption("Dots coloured by mean daily rainfall. Open **Map** to colour by anything and select catchments.")
    with right:
        st.markdown("##### What you can do")
        cards = [("pages/map", ":material/map:", "Map", "See every gauge. Colour by rainfall, aridity, baseflow… and click to select."),
                 ("pages/one", ":material/water:", "One catchment", "Hydrograph, flow duration curve, seasonal pattern, water balance, gaps and weather."),
                 ("pages/compare", ":material/compare_arrows:", "Compare", "Put up to 8 catchments on the same charts, scaled by area."),
                 ("pages/attributes", ":material/scatter_plot:", "Attributes", "Scatter plots, distributions and correlations across all catchments.")]
        for _, icon, title, text in cards:
            with st.container(border=True):
                st.page_link(PAGES[title], label=f"**{title}**", icon=icon)
                st.markdown(f"<span class='note'>{text}</span>", unsafe_allow_html=True)


def page_map():
    data, ids = DATA, IDS
    header("Map of catchments", "Colour the gauges by any attribute. Click a dot to select that catchment.")
    if not (data.lat_col and data.lon_col):
        st.info("No latitude / longitude columns were found, so the map cannot be drawn.")
        return
    num, txt = numeric_attrs(data), text_attrs(data)
    options = ["Nothing"] + txt + num
    default = next((c for c in ["aridity", "p_mean", "q_mean", "baseflow_index"] if c in num), "Nothing")
    c1, c2, c3 = st.columns([3, 1.2, 1.2])
    color_by = c1.selectbox("Colour the dots by", options, index=options.index(default),
                            format_func=lambda c: c if c == "Nothing" else nice(c), key="map_color")
    size_by_area = c2.toggle("Size by area", value=False, disabled=data.area_col is None)
    show_sel = c3.toggle("Show selected", value=True)
    fig = catchment_map(data, ids, None if color_by == "Nothing" else color_by, size_by_area,
                        highlight=st.session_state.get("cid") if show_sel else None, height=640)
    event = show(fig, 640, key="map", on_select="rerun", selection_mode="points")
    pts = event.get("selection", {}).get("points", []) if event else []
    pts = [p for p in pts if p.get("customdata")]
    if pts:
        cid = pts[0]["customdata"][0]
        if st.session_state.get("cid") != cid:
            st.session_state.cid = cid
            st.rerun()
    cid = st.session_state.get("cid")
    if cid in data.attributes.index:
        a, b = st.columns([4, 1])
        a.success(f"Selected: **{data.label(cid)}**", icon=":material/location_on:")
        b.page_link(PAGES["One catchment"], label="Open its data", icon=":material/arrow_forward:")
    with st.expander("Table of catchments on the map", icon=":material/table:"):
        att = data.attributes.loc[ids]
        cols = [c for c in ["Gauge ID", data.name_col, data.river_col, data.basin_col, data.state_col,
                            data.area_col, None if color_by == "Nothing" else color_by] if c]
        st.dataframe(att[list(dict.fromkeys(cols))].rename(columns=nice), width="stretch", hide_index=True, height=360)


def page_one():
    data, ids = DATA, IDS
    header("One catchment")
    cid = pick_catchment(data, ids)
    row = data.attributes.loc[cid]

    m = st.columns(6)
    m[0].metric("Gauge ID", str(row.get("Gauge ID", cid)))
    m[1].metric("River", fmt(row[data.river_col]) if data.river_col else "–")
    m[2].metric("Area (km²)", fmt(row[data.area_col]) if data.area_col else "–")
    m[3].metric("Rainfall (mm/day)", fmt(row.get("p_mean")))
    m[4].metric("Aridity index", fmt(row.get("aridity")))
    m[5].metric("Flow data available", f"{row['Observed flow available (%)']:.0f} %"
                if pd.notna(row.get("Observed flow available (%)", np.nan)) else "–")
    analysis_panel(cid)


@st.fragment
def analysis_panel(cid):
    """Runs on its own: changing a chart or option here does not reload the whole page."""
    data = DATA
    row = data.attributes.loc[cid]
    view = st.segmented_control("Chart", ["Hydrograph", "Flow duration", "Seasonal pattern", "Water balance",
                                          "Data gaps", "Weather", "Attributes", "Location", "Download"],
                                default="Hydrograph", key="view", label_visibility="collapsed")
    view = view or "Hydrograph"
    c2, c3, c4 = st.columns([1.3, 2.2, 5], vertical_alignment="bottom")
    units = c2.segmented_control("Units", ["m³/s", "mm/day"], default="m³/s", key="units",
                                 help="mm/day = flow divided by catchment area, so it can be compared with rainfall.")
    units = units or "m³/s"
    step = c3.segmented_control("Time step", ["Daily", "Monthly", "Yearly"], default="Daily", key="step")
    step = step or "Daily"

    daily = catchment_daily(ROOT, cid, "mm/day" if units == "mm/day" else "m3/s")
    if view == "Attributes":
        attribute_table(data, cid)
        return
    if view == "Location":
        show(catchment_map(data, [cid], highlight=cid, height=520, zoom=7), 520, key="loc_map")
        return
    if daily.empty:
        st.warning("No streamflow or rainfall time series were found for this catchment.")
        return

    start, end = daily.index.min().date(), daily.index.max().date()
    default_start = max(start, (pd.Timestamp(end) - pd.DateOffset(years=10)).date()) \
        if (step == "Daily" and view == "Hydrograph") else start
    rng = c4.slider("Period", min_value=start, max_value=end, value=(default_start, end),
                    format="YYYY-MM-DD", key=f"period_{cid}_{view}_{step}")
    daily = daily.loc[str(rng[0]):str(rng[1])]
    agg = aggregate(daily, step)
    flow_cols = [c for c in agg.columns if c != "Rainfall"]
    funit = "mm/day" if units == "mm/day" else "m³/s"
    runit = {"Daily": "mm/day", "Monthly": "mm/month", "Yearly": "mm/year"}[step]
    colors = {c: (OBS if "Observed" in c else MODEL if "Model" in c else PALETTE[2 + i]) for i, c in enumerate(flow_cols)}

    if view == "Hydrograph":
        has_rain = "Rainfall" in agg
        fig = make_subplots(rows=2 if has_rain else 1, cols=1, shared_xaxes=True,
                            row_heights=[0.28, 0.72] if has_rain else [1], vertical_spacing=0.03)
        gl = len(agg) > 2000
        r = 1
        if has_rain:
            if len(agg) > 400:
                fig.add_trace(go.Scatter(x=agg.index, y=agg["Rainfall"], name="Rainfall", mode="lines",
                                         fill="tozeroy", fillcolor="rgba(141,185,234,0.55)",
                                         line=dict(color=RAIN, width=0.6)), row=1, col=1)
            else:
                fig.add_trace(go.Bar(x=agg.index, y=agg["Rainfall"], name="Rainfall", marker_color=RAIN,
                                     marker_line_width=0), row=1, col=1)
            fig.update_yaxes(autorange="reversed", title_text=f"Rain ({runit})", row=1, col=1)
            r = 2
        for c in reversed(flow_cols):           # observed drawn last = on top
            fig.add_trace(line(agg.index, agg[c], c, colors[c], 1.6 if "Observed" in c else 1.2, gl), row=r, col=1)
        log = st.toggle("Log scale for flow", key="log_hydro")
        fig.update_yaxes(title_text=f"Flow ({funit})", type="log" if log else "linear", row=r, col=1)
        fig.update_layout(hovermode="x unified", legend_traceorder="reversed")
        show(fig, 580, key="hydro")
        if len(flow_cols) >= 2:
            o, s = daily[flow_cols[0]], daily[flow_cols[1]]
            ok = o.notna() & s.notna()
            if ok.sum() > 30:
                nse = 1 - ((o[ok] - s[ok]) ** 2).sum() / ((o[ok] - o[ok].mean()) ** 2).sum()
                st.caption(f"How well the LSTM model matches observed flow in this period (daily): "
                           f"Nash–Sutcliffe efficiency **{nse:.2f}** (1 = perfect, below 0 = poor).")
        st.caption("Drag on the chart to zoom, double-click to reset. Camera icon (top right) saves a high-resolution PNG.")

    elif view == "Flow duration":
        fig = go.Figure()
        for c in flow_cols:
            x, y = flow_duration(daily[c])
            fig.add_trace(line(x, y, c, colors[c], 2.2))
        fig.update_yaxes(type="log", title_text=f"Daily flow ({funit})")
        fig.update_xaxes(title_text="Percent of time flow is equalled or exceeded (%)", range=[0, 100])
        show(fig, 480, key="fdc")
        st.caption("Left = rare floods, right = dry-season low flows. A steep curve means a flashy river; "
                   "a flat curve means steady flow fed by groundwater.")

    elif view == "Seasonal pattern":
        mon = daily.groupby(daily.index.month).mean()
        a, b = st.columns(2, gap="medium")
        if "Rainfall" in mon:
            fig = go.Figure(go.Bar(x=MONTHS, y=mon["Rainfall"].values, marker_color=RAIN, name="Rainfall",
                                   marker_line_width=0))
            fig.update_yaxes(title_text="Mean rainfall (mm/day)")
            fig.update_layout(title=dict(text="Rainfall", font=dict(size=14)), showlegend=False, bargap=0.25)
            with a:
                show(fig, 400, key="mon_rain")
        fig = go.Figure()
        for c in flow_cols:
            fig.add_trace(go.Scatter(x=MONTHS, y=mon[c].values, name=c, mode="lines+markers",
                                     line=dict(color=colors[c], width=2), marker=dict(size=8)))
        fig.update_yaxes(title_text=f"Mean flow ({funit})", rangemode="tozero")
        fig.update_layout(title=dict(text="Streamflow", font=dict(size=14)))
        with b if "Rainfall" in mon else a:
            show(fig, 400, key="mon_flow")
        st.caption("Average of every January, every February, and so on, over the chosen period.")

    elif view == "Water balance":
        area = row[data.area_col] if data.area_col else np.nan
        q = daily[flow_cols[0]] if (flow_cols and units == "mm/day") else \
            (to_mm_per_day(daily[flow_cols[0]], area) if flow_cols else None)
        if q is None or "Rainfall" not in daily:
            st.info("Needs rainfall, streamflow and the catchment area to work out the water balance.")
        else:
            yr = pd.DataFrame({"Rainfall": daily["Rainfall"].resample("YS").sum(min_count=300),
                               "Runoff": q.resample("YS").sum(min_count=300)})
            yr["Runoff ratio"] = yr["Runoff"] / yr["Rainfall"]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=yr.index.year, y=yr["Rainfall"], name="Rainfall", marker_color=RAIN, marker_line_width=0))
            fig.add_trace(go.Bar(x=yr.index.year, y=yr["Runoff"], name="Runoff (flow ÷ area)", marker_color=OBS, marker_line_width=0))
            fig.update_layout(barmode="group", bargap=0.2, bargroupgap=0.08)
            fig.update_yaxes(title_text="Water depth (mm/year)")
            show(fig, 400, key="wb")
            fig = go.Figure(go.Scatter(x=yr.index.year, y=yr["Runoff ratio"], mode="lines+markers", name="Runoff ratio",
                                       line=dict(color=INK2, width=2), marker=dict(size=8)))
            mean_rr = yr["Runoff ratio"].mean()
            fig.add_hline(y=mean_rr, line=dict(color="#9aa1ad", dash="dot", width=1),
                          annotation_text=f"average {mean_rr:.2f}", annotation_position="top left")
            fig.update_yaxes(title_text="Runoff ratio", rangemode="tozero")
            fig.update_layout(showlegend=False, title=dict(text="Runoff ratio = runoff ÷ rainfall", font=dict(size=14)))
            show(fig, 300, key="rr")
            st.caption("Years with fewer than 300 days of data are left out.")

    elif view == "Data gaps":
        if flow_cols:
            obs = daily[flow_cols[0]]
            g = obs.notna().groupby([obs.index.year, obs.index.month]).mean().unstack().reindex(columns=range(1, 13)) * 100
            fig = go.Figure(go.Heatmap(z=g.values, x=MONTHS, y=g.index, colorscale=SEQ, zmin=0, zmax=100,
                                       xgap=2, ygap=2, colorbar=dict(title=dict(text="% days", side="right"), thickness=12),
                                       hovertemplate="%{y} %{x}: %{z:.0f}% of days<extra></extra>"))
            fig.update_yaxes(autorange="reversed", showline=False, ticks="")
            fig.update_xaxes(showline=False, ticks="", side="top")
            fig.update_layout(plot_bgcolor="#f3f4f6")
            show(fig, max(360, 17 * len(g)), key="gaps")
            st.caption(f"Share of days with {flow_cols[0].lower()} in each month. Grey = no data at all.")

    elif view == "Weather":
        f = catchment_forcing(ROOT, cid)
        if f.empty:
            st.info("No weather (forcing) file was found for this catchment.")
        else:
            f = f.loc[str(rng[0]):str(rng[1])]
            vars_ = st.multiselect("Variables", list(f.columns), default=list(f.columns[:3]), format_func=nice, key="wvars")
            if vars_:
                fa = f[vars_].resample({"Daily": "D", "Monthly": "MS", "Yearly": "YS"}[step]).mean()
                fig = make_subplots(rows=len(vars_), cols=1, shared_xaxes=True, vertical_spacing=0.04)
                for i, v in enumerate(vars_):
                    fig.add_trace(line(fa.index, fa[v], nice(v), PALETTE[i % 8], 1.2, len(fa) > 2000), row=i + 1, col=1)
                    fig.update_yaxes(title_text=nice(v), row=i + 1, col=1, title_font=dict(size=12))
                fig.update_layout(hovermode="x unified", showlegend=False)
                show(fig, 140 + 190 * len(vars_), key="weather")

    elif view == "Download":
        out = daily.copy()
        f = catchment_forcing(ROOT, cid)
        if not f.empty:
            out = out.join(f.loc[str(rng[0]):str(rng[1])].rename(columns=nice), how="outer", rsuffix=" (weather)")
        out.index.name = "Date"
        st.dataframe(out.head(500), width="stretch", height=380)
        st.download_button("Download daily data (CSV)", out.to_csv().encode(), type="primary",
                           icon=":material/download:",
                           file_name=f"CAMELS-IND {row.get('Gauge ID', cid)} daily.csv", mime="text/csv")


def attribute_table(data, cid):
    row = data.attributes.loc[cid].drop(labels=["Gauge ID"], errors="ignore")
    t = pd.DataFrame({"Group": [data.attribute_groups.get(c, "Other") for c in row.index],
                      "Attribute": [nice(c) for c in row.index],
                      "Value": [fmt(v, 3) if not isinstance(v, str) else v for v in row.values],
                      "Column in file": row.index})
    search = st.text_input("Search attributes", placeholder="e.g. rain, soil, dam", key="attr_search",
                           icon=":material/search:")
    if search:
        t = t[t["Attribute"].str.contains(search, case=False) | t["Column in file"].str.contains(search, case=False)]
    groups = list(dict.fromkeys(t["Group"]))
    if not groups:
        st.info("No attributes match.")
        return
    tabs = st.tabs([f"{g} ({(t['Group'] == g).sum()})" for g in groups])
    for tab, g in zip(tabs, groups):
        with tab:
            st.dataframe(t[t["Group"] == g].drop(columns="Group"), width="stretch", hide_index=True)


def page_compare():
    data, ids = DATA, IDS
    header("Compare catchments", "Flows are in mm/day (flow ÷ catchment area) so big and small catchments compare fairly.")
    default = [c for c in [st.session_state.get("cid")] if c in ids] or ids[:2]
    picks = st.multiselect("Pick up to 8 catchments", ids, default=default[:8], max_selections=8,
                           format_func=data.label, key="cmp_picks")
    if not picks:
        st.info("Pick at least one catchment.")
        return
    kinds = list(data.streamflow_files)
    kind = kinds[0] if kinds else None
    c1, c2 = st.columns([3, 2])
    view = c1.segmented_control("Chart", ["Seasonal pattern", "Flow duration", "Yearly runoff", "Attributes"],
                                default="Seasonal pattern", key="cmp_view", label_visibility="collapsed") or "Seasonal pattern"
    if len(kinds) > 1:
        kind = c2.segmented_control("Streamflow", kinds, default=kinds[0], key="cmp_kind") or kinds[0]

    if view == "Attributes":
        num = numeric_attrs(data)
        default_cols = [c for c in ["p_mean", "pet_mean", "aridity", "q_mean", "runoff_ratio", "baseflow_index",
                                    "slope_fdc", "elev_mean", "forest_frac", data.area_col] if c in num]
        cols = st.multiselect("Attributes", num, default=default_cols or num[:8], format_func=nice, key="cmp_cols")
        if cols:
            t = data.attributes.loc[picks, cols].T
            t.columns = [data.label(c) for c in picks]
            t.index = [nice(c) for c in t.index]
            st.dataframe(t.style.format(precision=3), width="stretch")
        return

    series = {}
    for cid in picks:
        d = catchment_daily(ROOT, cid, "mm/day")
        if kind in d:
            series[data.label(cid)] = d[kind]
    if not series:
        st.warning("No streamflow found for these catchments.")
        return
    df = pd.DataFrame(series)
    fig = go.Figure()
    if view == "Seasonal pattern":
        mon = df.groupby(df.index.month).mean()
        for i, c in enumerate(mon.columns):
            fig.add_trace(go.Scatter(x=MONTHS, y=mon[c].values, name=c, mode="lines+markers",
                                     line=dict(width=2, color=PALETTE[i]), marker=dict(size=8)))
        fig.update_yaxes(title_text="Mean flow (mm/day)", rangemode="tozero")
    elif view == "Flow duration":
        for i, c in enumerate(df.columns):
            x, y = flow_duration(df[c])
            fig.add_trace(line(x, y, c, PALETTE[i], 2))
        fig.update_yaxes(type="log", title_text="Daily flow (mm/day)")
        fig.update_xaxes(title_text="Percent of time flow is equalled or exceeded (%)", range=[0, 100])
    else:
        yr = df.resample("YS").sum(min_count=300)
        for i, c in enumerate(yr.columns):
            fig.add_trace(go.Scatter(x=yr.index.year, y=yr[c], name=c, mode="lines+markers",
                                     line=dict(width=2, color=PALETTE[i]), marker=dict(size=7)))
        fig.update_yaxes(title_text="Yearly runoff (mm/year)", rangemode="tozero")
        st.caption("Years with fewer than 300 days of data are left out.")
    show(fig, 500, key="cmp_fig")


def page_attributes():
    data, ids = DATA, IDS
    header("Catchment attributes", "Look for patterns across all catchments in the current filter.")
    att = data.attributes.loc[ids].copy()
    att["Name"] = [data.label(i) for i in att.index]
    num, txt = numeric_attrs(data), text_attrs(data)
    if len(num) < 2:
        st.info("Not enough numeric attributes were found.")
        return
    view = st.segmented_control("Chart", ["Scatter", "Distribution", "Correlation", "Table"], default="Scatter",
                                key="att_view", label_visibility="collapsed") or "Scatter"

    def idx(name, fallback):
        return num.index(name) if name in num else fallback

    lab = {k: nice(k) for k in att.columns}
    if view == "Scatter":
        c = st.columns([2, 2, 2, 1.2])
        x = c[0].selectbox("X axis", num, index=idx("aridity", 0), format_func=nice, key="sx")
        y = c[1].selectbox("Y axis", num, index=idx("runoff_ratio", 1), format_func=nice, key="sy")
        colr = c[2].selectbox("Colour", ["Nothing"] + txt + num, format_func=lambda v: v if v == "Nothing" else nice(v), key="sc")
        logs = c[3].pills("Log axes", ["X", "Y"], selection_mode="multi", key="slog")
        plot = att.copy()
        kw = {}
        if colr != "Nothing":
            if pd.api.types.is_numeric_dtype(plot[colr]):
                kw = dict(color=colr, color_continuous_scale=SEQ)
            else:
                top = list(plot[colr].astype(str).value_counts().index[:3])   # max 3 groups stay distinct
                plot[colr] = plot[colr].astype(str).where(plot[colr].astype(str).isin(top), "Other")
                kw = dict(color=colr, color_discrete_sequence=PALETTE[:3] + ["#a3a9b3"],
                          category_orders={colr: top + ["Other"]})
        fig = px.scatter(plot, x=x, y=y, hover_name="Name", log_x="X" in (logs or []), log_y="Y" in (logs or []),
                         labels=lab, custom_data=[plot.index], **kw)
        if not kw:
            fig.update_traces(marker=dict(color=OBS))
        fig.update_traces(marker=dict(size=9, opacity=0.85, line=dict(width=1, color="white")))
        fig.update_layout(coloraxis_colorbar=dict(thickness=12, title=dict(side="right")))
        ok = att[[x, y]].dropna()
        if len(ok) > 3:
            r = ok[x].corr(ok[y], method="spearman")
            st.caption(f"Spearman rank correlation **{r:.2f}** across {len(ok)} catchments "
                       "(near ±1 = strong link, near 0 = no link). Click a dot to select that catchment.")
        event = show(fig, 560, key="scatter_attr", on_select="rerun", selection_mode="points")
        pts = event.get("selection", {}).get("points", []) if event else []
        if pts and pts[0].get("customdata"):
            st.session_state.cid = pts[0]["customdata"][0]
            a, b = st.columns([4, 1])
            a.success(f"Selected **{data.label(st.session_state.cid)}**", icon=":material/location_on:")
            b.page_link(PAGES["One catchment"], label="Open its data", icon=":material/arrow_forward:")

    elif view == "Distribution":
        c = st.columns(2)
        v = c[0].selectbox("Attribute", num, index=idx("p_mean", 0), format_func=nice, key="hist_v")
        by = c[1].selectbox("Split by", ["Nothing"] + (txt if txt else []),
                            format_func=lambda s: s if s == "Nothing" else nice(s), key="hist_by")
        g1, g2 = st.columns(2, gap="medium")
        fig = px.histogram(att, x=v, nbins=30, labels=lab, color_discrete_sequence=[OBS])
        fig.update_traces(marker_line_color="white", marker_line_width=1.5)
        fig.update_layout(bargap=0.05, title=dict(text="How many catchments", font=dict(size=14)))
        fig.update_yaxes(title_text="Number of catchments")
        with g1:
            show(fig, 440, key="hist")
        if by == "Nothing":
            fig = px.box(att, y=v, points="all", hover_name="Name", labels=lab, color_discrete_sequence=[OBS])
        else:
            order = att.groupby(by)[v].median().sort_values().index.astype(str).tolist()
            fig = px.box(att.assign(**{by: att[by].astype(str)}), x=by, y=v, points="all", hover_name="Name",
                         labels=lab, color_discrete_sequence=[OBS], category_orders={by: order})
        fig.update_traces(marker=dict(size=5, opacity=0.6), line=dict(width=1.5))
        fig.update_layout(showlegend=False, title=dict(text="Spread", font=dict(size=14)))
        with g2:
            show(fig, 440, key="box")

    elif view == "Correlation":
        default = [c for c in ["p_mean", "pet_mean", "aridity", "high_prec_freq", "q_mean", "runoff_ratio",
                               "baseflow_index", "slope_fdc", "elev_mean", "slope_mean", "forest_frac"] if c in num]
        cols = st.multiselect("Attributes to include", num, default=default or num[:10], format_func=nice, key="corr_cols")
        if len(cols) >= 2:
            corr = att[cols].corr(method="spearman")
            names = [nice(c) for c in cols]
            fig = go.Figure(go.Heatmap(z=corr.values, x=names, y=names, zmin=-1, zmax=1, xgap=2, ygap=2,
                                       colorscale=[[0, "#2a78d6"], [0.5, "#f1f1f1"], [1, "#e34948"]],
                                       text=np.round(corr.values, 2), texttemplate="%{text}",
                                       textfont=dict(size=11, color=INK),
                                       hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
                                       colorbar=dict(thickness=12)))
            fig.update_yaxes(autorange="reversed", showline=False, ticks="")
            fig.update_xaxes(showline=False, ticks="", tickangle=-35)
            show(fig, 200 + 44 * len(cols), key="corr")
            st.caption("Spearman rank correlation. Red = both rise together; blue = one rises as the other falls.")

    else:
        show_df = att.drop(columns=["Name"]).rename(columns=nice)
        st.dataframe(show_df, width="stretch", hide_index=True, height=520)
        st.download_button("Download this table (CSV)", show_df.to_csv(index=False).encode(), icon=":material/download:",
                           file_name="CAMELS-IND attributes.csv", mime="text/csv")


def page_about():
    data = DATA
    header("About the data")
    st.markdown("""
**CAMELS-IND** (Catchment Attributes and MEteorology for Large-sample Studies – India) provides daily streamflow,
catchment-average weather and about 200 catchment attributes for **472 catchments in Peninsular India, 1980–2020**,
including LSTM-model streamflow for every catchment.

Source: Mangukiya et al. (2025), *Earth System Science Data* 17, 461–491,
[doi:10.5194/essd-17-461-2025](https://doi.org/10.5194/essd-17-461-2025) · Data on
[Zenodo](https://zenodo.org/records/14999580). Please cite the paper if you use the data.
""")
    st.markdown("##### What the app found in the data folder")
    rows = [("Folder", str(data.root)),
            ("Catchments", f"{len(data.attributes)}"),
            ("Attribute columns", f"{len(data.attributes.columns) - 1}"),
            ("Streamflow files", ", ".join(f"{k} ({Path(v).name})" for k, v in data.streamflow_files.items()) or "none"),
            ("Weather (forcing) files", f"{len(data.forcing_files)} catchments"),
            ("Shapefiles", f"{len(data.shapefiles)}")]
    st.dataframe(pd.DataFrame(rows, columns=["Item", "Found"]), hide_index=True, width="stretch")
    for n in data.notes:
        st.caption(n)


def page_welcome():
    st.markdown("""<div class='hero'><h1>💧 CAMELS-IND Explorer</h1>
    <p>Daily streamflow, weather and catchment attributes for 472 river catchments in Peninsular India,
    1980–2020 — explore it without writing code.</p></div>""", unsafe_allow_html=True)
    a, b = st.columns([3, 2], gap="large")
    with a:
        st.markdown("#### Load the data to begin")
        st.markdown("The easiest way is **Download from Zenodo** – the app fetches the official release once "
                    "and keeps a copy. You can also point it at a folder on your computer or upload the zip.")
        data_loader_panel(expanded=True)
    with b:
        with st.container(border=True):
            st.markdown("**What's inside**\n\n- Map of all gauges, coloured by any attribute\n"
                        "- Hydrographs with rainfall, flow duration curves, seasonal patterns\n"
                        "- Yearly water balance and data-gap charts\n- Compare up to 8 catchments\n"
                        "- Scatter, distribution and correlation charts of ~200 attributes\n- CSV downloads")


# ============================================================================= main
if "root" not in st.session_state:
    st.session_state.root = default_folder()
ROOT = st.session_state.root

if not ROOT:
    st.navigation([st.Page(page_welcome, title="Welcome", icon=":material/home:")]).run()
    st.stop()

DATA = open_dataset(ROOT)
if DATA.attributes.empty:
    st.error("No CAMELS-IND files were recognised in that folder.")
    data_loader_panel(expanded=True)
    st.stop()

PAGES = {
    "Home": st.Page(page_home, title="Home", icon=":material/home:", url_path="home", default=True),
    "Map": st.Page(page_map, title="Map", icon=":material/map:", url_path="map"),
    "One catchment": st.Page(page_one, title="One catchment", icon=":material/water:", url_path="catchment"),
    "Compare": st.Page(page_compare, title="Compare", icon=":material/compare_arrows:", url_path="compare"),
    "Attributes": st.Page(page_attributes, title="Attributes", icon=":material/scatter_plot:", url_path="attributes"),
    "About the data": st.Page(page_about, title="About the data", icon=":material/info:", url_path="about"),
}
nav = st.navigation(list(PAGES.values()))
with st.sidebar:
    IDS = sidebar_filters(DATA)
    st.divider()
    data_loader_panel(expanded=False)
nav.run()
