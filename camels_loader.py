"""
Finds and reads the CAMELS-IND files, wherever they sit inside a folder.

The CAMELS-IND zip from Zenodo has three kinds of files:
  1. Attribute tables  - one row per catchment (topography, climate, soil ...)
  2. Streamflow tables - one column per catchment, one row per day
  3. Forcing files     - one file per catchment, one row per day (rain, temperature ...)
This module looks at every CSV/XLSX in the folder and works out which kind it is,
so the app keeps working even if the folder layout changes between versions.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ZENODO_RECORD = "14999580"
ZENODO_FILES = {
    "Catchments with good streamflow (242 catchments, about 180 MB)":
        "CAMELS_IND_Catchments_Streamflow_Sufficient.zip",
    "All catchments (472 catchments, about 350 MB)":
        "CAMELS_IND_All_Catchments.zip",
}

ID_COLUMN_NAMES = ["gauge_id", "gaugeid", "gauge", "station_id", "stationid", "id", "catchment_id"]


# --------------------------------------------------------------------------- helpers
def canonical_id(value) -> str:
    """Turn '03001', 3001, '3001.0' into the same key so files match each other."""
    s = str(value).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s.lower()


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def find_id_column(columns) -> str | None:
    normed = {_norm(c): c for c in columns}
    for cand in ID_COLUMN_NAMES:
        if _norm(cand) in normed:
            return normed[_norm(cand)]
    return None


def build_dates(df: pd.DataFrame) -> pd.DatetimeIndex | None:
    """Return a date index from a 'date' column or from year/month/day columns."""
    cols = {_norm(c): c for c in df.columns}
    for key in ("date", "datetime", "time", "dates"):
        if key in cols:
            d = pd.to_datetime(df[cols[key]], errors="coerce", dayfirst=False)
            if d.notna().mean() > 0.9:
                return pd.DatetimeIndex(d)
    y = cols.get("year") or cols.get("yr") or cols.get("yyyy")
    m = cols.get("month") or cols.get("mnth") or cols.get("mm")
    d = cols.get("day") or cols.get("dd")
    if y and m and d:
        return pd.DatetimeIndex(pd.to_datetime(
            dict(year=df[y], month=df[m], day=df[d]), errors="coerce"))
    return None


def date_like_columns(columns) -> set:
    keys = {"date", "datetime", "time", "dates", "year", "yr", "yyyy",
            "month", "mnth", "mm", "day", "dd", "doy", "jday"}
    return {c for c in columns if _norm(c) in keys}


def _read_table(path: Path, nrows=None) -> dict[str, pd.DataFrame]:
    """Read a CSV / TXT / XLSX. Returns {table name: dataframe}."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None, nrows=nrows, dtype={"gauge_id": str})
        return {f"{path.stem} / {k}": v for k, v in sheets.items()}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        first = f.readline()
    sep = max([",", ";", "\t", "|"], key=first.count)
    df = pd.read_csv(path, sep=sep, nrows=nrows, dtype=str, low_memory=False)
    return {path.stem: df}


def _to_numeric_where_possible(df: pd.DataFrame, keep_text=()) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c in keep_text:
            continue
        conv = pd.to_numeric(out[c], errors="coerce")
        # keep as number if most non-empty values converted fine
        nonempty = out[c].notna() & (out[c].astype(str).str.strip() != "")
        if nonempty.sum() == 0 or conv[nonempty].notna().mean() >= 0.9:
            out[c] = conv
    return out


# --------------------------------------------------------------------------- dataset
@dataclass
class CamelsData:
    root: Path
    attributes: pd.DataFrame = field(default_factory=pd.DataFrame)       # index = canonical id
    attribute_groups: dict = field(default_factory=dict)                 # column -> group name
    streamflow_files: dict = field(default_factory=dict)                 # kind -> path
    forcing_files: dict = field(default_factory=dict)                    # canonical id -> path
    shapefiles: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    # ---------- key columns --------------------------------------------------
    def _pick(self, patterns, numeric=None):
        cols = list(self.attributes.columns)
        for p in patterns:
            for c in cols:
                if re.fullmatch(p, c.lower()):
                    if numeric is None or pd.api.types.is_numeric_dtype(self.attributes[c]) == numeric:
                        return c
        for p in patterns:
            for c in cols:
                if re.search(p, c.lower()):
                    if numeric is None or pd.api.types.is_numeric_dtype(self.attributes[c]) == numeric:
                        return c
        return None

    @property
    def lat_col(self):
        return self._pick([r"cwc_lat", r"gauge_lat", r"lat_outlet", r"lat", r"latitude", r".*lat.*"], numeric=True)

    @property
    def lon_col(self):
        return self._pick([r"cwc_lon", r"gauge_lon", r"lon_outlet", r"lon", r"long", r"longitude", r".*lon.*"], numeric=True)

    @property
    def name_col(self):
        return self._pick([r"cwc_site_name", r"site_name", r"station_name", r"gauge_name", r".*name.*"], numeric=False)

    @property
    def river_col(self):
        return self._pick([r"cwc_river", r"river", r"river_name", r".*river.*"], numeric=False)

    @property
    def basin_col(self):
        return self._pick([r"cwc_basin", r"basin", r"basin_name", r".*basin.*"], numeric=False)

    @property
    def state_col(self):
        return self._pick([r"cwc_state", r"state", r".*state.*"], numeric=False)

    @property
    def area_col(self):
        return self._pick([r"cwc_area", r"ghi_area", r"area_gages2", r"area", r".*area.*"], numeric=True)

    def label(self, cid: str) -> str:
        """Short text used in dropdowns, e.g. '3001 - Tikarapara (Mahanadi)'."""
        row = self.attributes.loc[cid] if cid in self.attributes.index else None
        orig = row["Gauge ID"] if row is not None and "Gauge ID" in row else cid
        parts = [str(orig)]
        if row is not None:
            if self.name_col and pd.notna(row.get(self.name_col)):
                parts.append(str(row[self.name_col]).title())
            if self.river_col and pd.notna(row.get(self.river_col)):
                parts.append(f"({str(row[self.river_col]).title()})")
        return " - ".join(parts[:2]) + (" " + parts[2] if len(parts) > 2 else "")

    # ---------- time series ---------------------------------------------------
    def streamflow(self, cid: str, kind: str) -> pd.Series | None:
        path = self.streamflow_files.get(kind)
        if path is None:
            return None
        wide = load_wide_table(str(path))
        col = wide["map"].get(cid)
        if col is None:
            return None
        return wide["df"][col].rename(kind)

    def forcing(self, cid: str) -> pd.DataFrame | None:
        path = self.forcing_files.get(cid)
        if path is None:
            return None
        return load_forcing(str(path))

    def rain_column(self, forcing: pd.DataFrame) -> str | None:
        for p in [r"prcp.*", r"precip.*", r"rain.*", r"pr", r"p", r"ppt.*", r".*prcp.*", r".*precip.*", r".*rain.*"]:
            for c in forcing.columns:
                if re.fullmatch(p, c.lower().split("(")[0].strip()):
                    return c
        return None


# --------------------------------------------------------------------------- cached loaders
_WIDE_CACHE: dict = {}
_FORCING_CACHE: dict = {}
PARQUET_DIR = Path(os.environ.get("CAMELS_CACHE", Path.home() / ".camels_ind_cache")) / "parquet"


def fast_read_csv(path: str) -> pd.DataFrame:
    """Fast CSV read (C engine). Guesses the separator from the first line."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        first = f.readline()
    sep = max([",", ";", "\t", "|"], key=first.count)
    if first.count(sep) == 0:
        sep = r"\s+"
    return pd.read_csv(path, sep=sep, engine="c" if sep != r"\s+" else "python", low_memory=False)


def _parquet_path(path: str) -> Path:
    st_ = os.stat(path)
    key = f"{abs(hash(os.path.abspath(path)))}_{int(st_.st_mtime)}_{st_.st_size}"
    return PARQUET_DIR / f"{Path(path).stem}_{key}.parquet"


def load_wide_table(path: str) -> dict:
    """Streamflow file: rows = days, columns = catchments."""
    if path in _WIDE_CACHE:
        return _WIDE_CACHE[path]
    pq = _parquet_path(path)
    df = None
    if pq.exists():
        try:
            df = pd.read_parquet(pq)
        except Exception:  # noqa: BLE001
            df = None
    if df is None:
        df = fast_read_csv(path)
        dates = build_dates(df)
        df = df.drop(columns=list(date_like_columns(df.columns)))
        df = df.apply(pd.to_numeric, errors="coerce").astype("float32")
        df.index = dates
        df = df[~df.index.isna()]
        df[df < 0] = np.nan          # -999 style missing values
        df.columns = [str(c) for c in df.columns]
        try:
            PARQUET_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(pq)
        except Exception:  # noqa: BLE001
            pass
    mapping = {canonical_id(c): c for c in df.columns}
    _WIDE_CACHE[path] = {"df": df, "map": mapping}
    return _WIDE_CACHE[path]


def load_forcing(path: str) -> pd.DataFrame:
    if path in _FORCING_CACHE:
        return _FORCING_CACHE[path]
    df = fast_read_csv(path)
    dates = build_dates(df)
    df = df.drop(columns=list(date_like_columns(df.columns)))
    idc = find_id_column(df.columns)
    if idc:
        df = df.drop(columns=[idc])
    df = df.apply(pd.to_numeric, errors="coerce")
    df.index = dates
    df = df[~df.index.isna()]
    df = df.mask(df <= -999)
    if len(_FORCING_CACHE) > 60:
        _FORCING_CACHE.clear()
    _FORCING_CACHE[path] = df
    return df


# --------------------------------------------------------------------------- scanning
GROUP_WORDS = {
    "name": "Location and names", "topo": "Topography", "clim": "Climate",
    "hydro": "Hydrological signatures", "land": "Land cover", "soil": "Soil",
    "geol": "Geology", "anth": "Human influence", "hum": "Human influence",
}


def _group_from_name(stem: str) -> str:
    s = stem.lower()
    for k, v in GROUP_WORDS.items():
        if re.search(rf"(^|[_\-\s/]){k}", s):
            return v
    return stem.replace("_", " ").title()


def scan_folder(root: str | Path) -> CamelsData:
    root = Path(root)
    data = CamelsData(root=root)
    files = [p for p in root.rglob("*") if p.is_file() and not p.name.startswith(("._", "~$"))]
    tables = [p for p in files if p.suffix.lower() in (".csv", ".txt", ".xlsx", ".xls")]
    data.shapefiles = [p for p in files if p.suffix.lower() == ".shp"]

    # files whose name is just a gauge id -> per-catchment forcing files
    per_catchment = {}
    for p in tables:
        stem = p.stem
        m = re.fullmatch(r"(?:[a-z_]*?_)?(\d{3,8})(?:_[a-z_]+)?", stem.lower())
        if m and "attribute" not in stem.lower():
            per_catchment.setdefault(canonical_id(m.group(1)), []).append(p)

    attr_frames = []
    for p in tables:
        if any(p in v for v in per_catchment.values()):
            continue
        try:
            heads = _read_table(p, nrows=5)
        except Exception as e:  # noqa: BLE001
            data.notes.append(f"Could not read {p.name}: {e}")
            continue
        for tname, head in heads.items():
            cols = list(head.columns)
            idc = find_id_column(cols)
            has_dates = build_dates(head) is not None
            n_numeric_headers = sum(bool(re.fullmatch(r"\d{3,8}(\.0)?", str(c).strip())) for c in cols)
            if has_dates and n_numeric_headers >= 1:
                low = tname.lower()
                if any(w in low for w in ("sim", "lstm", "pred", "model")):
                    kind = "Model (LSTM) streamflow"
                elif "flow" in low or "discharge" in low or "q" == low:
                    kind = "Observed streamflow"
                else:
                    kind = tname.replace("_", " ").title()
                if kind in data.streamflow_files:
                    kind = f"{kind} ({p.stem})"
                if p.suffix.lower() in (".csv", ".txt"):
                    data.streamflow_files[kind] = p
                continue
            if idc and not has_dates:
                full = _read_table(p)[tname]
                full = full.rename(columns={idc: "Gauge ID"})
                full["Gauge ID"] = full["Gauge ID"].astype(str).str.strip()
                full["_cid"] = full["Gauge ID"].map(canonical_id)
                full = full.drop_duplicates("_cid").set_index("_cid")
                full = _to_numeric_where_possible(full, keep_text=("Gauge ID",))
                group = _group_from_name(tname.split(" / ")[-1] if " / " in tname else tname)
                attr_frames.append((group, full))

    # merge attribute tables
    if attr_frames:
        merged = None
        for group, frame in attr_frames:
            for c in frame.columns:
                if c != "Gauge ID" and c not in data.attribute_groups:
                    data.attribute_groups[c] = group
            if merged is None:
                merged = frame
            else:
                new_cols = [c for c in frame.columns if c not in merged.columns]
                merged = merged.join(frame[new_cols], how="outer")
                if "Gauge ID" in frame:
                    merged["Gauge ID"] = merged["Gauge ID"].fillna(frame["Gauge ID"])
        data.attributes = merged

    # forcing files
    for cid, paths in per_catchment.items():
        pick = sorted(paths, key=lambda q: (("forc" not in str(q).lower() and "met" not in str(q).lower()), len(str(q))))[0]
        data.forcing_files[cid] = pick

    # make sure every catchment that has any data is in the attribute table
    ids = set(data.attributes.index) if not data.attributes.empty else set()
    ids |= set(data.forcing_files)
    for path in data.streamflow_files.values():
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                first = f.readline()
            header = pd.read_csv(io.StringIO(first), sep=max([",", ";", "\t"], key=first.count)).columns
            ids |= {canonical_id(c) for c in header if c not in date_like_columns(header)}
        except Exception:  # noqa: BLE001
            pass
    if data.attributes.empty:
        data.attributes = pd.DataFrame(index=sorted(ids))
        data.attributes["Gauge ID"] = data.attributes.index
    else:
        missing = sorted(ids - set(data.attributes.index))
        if missing:
            add = pd.DataFrame(index=missing)
            add["Gauge ID"] = missing
            data.attributes = pd.concat([data.attributes, add])
    data.attributes.index.name = "cid"
    order = sorted(data.attributes.index, key=lambda s: (0, int(s), "") if s.isdigit() else (1, 0, s))
    data.attributes = data.attributes.loc[order]
    return data


# --------------------------------------------------------------------------- zenodo download
def download_from_zenodo(file_name: str, dest_dir: str | Path, progress=None) -> Path:
    """Download and unzip one CAMELS-IND zip from Zenodo. Returns the unzip folder."""
    import requests

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_dir = dest_dir / Path(file_name).stem
    if (out_dir / ".done").exists():
        return out_dir
    url = f"https://zenodo.org/records/{ZENODO_RECORD}/files/{file_name}?download=1"
    zip_path = dest_dir / file_name
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    # nested zips inside the main zip
    for inner in list(out_dir.rglob("*.zip")):
        try:
            with zipfile.ZipFile(inner) as z:
                z.extractall(inner.with_suffix(""))
            inner.unlink()
        except zipfile.BadZipFile:
            pass
    zip_path.unlink(missing_ok=True)
    (out_dir / ".done").write_text("ok")
    return out_dir


def extract_uploaded_zip(file_bytes: bytes, dest_dir: str | Path) -> Path:
    dest_dir = Path(dest_dir)
    out_dir = dest_dir / "uploaded"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        z.extractall(out_dir)
    return out_dir


# --------------------------------------------------------------------------- catchment boundary
def catchment_outline(data: CamelsData, cid: str):
    """Return list of (lons, lats) rings for the catchment, or None."""
    try:
        import shapefile  # pyshp
    except ImportError:
        return None
    for shp in data.shapefiles:
        try:
            r = shapefile.Reader(str(shp))
        except Exception:  # noqa: BLE001
            continue
        fields = [f[0] for f in r.fields[1:]]
        idx = None
        if canonical_id(re.sub(r"\D", "", shp.stem) or "x") == cid and len(r) == 1:
            idx = 0
        else:
            idf = find_id_column(fields)
            if idf is not None:
                k = fields.index(idf)
                for i, rec in enumerate(r.iterRecords()):
                    if canonical_id(rec[k]) == cid:
                        idx = i
                        break
        if idx is None:
            continue
        shape = r.shape(idx)
        pts = np.array(shape.points)
        if pts.size == 0 or not (np.abs(pts[:, 0]).max() <= 180 and np.abs(pts[:, 1]).max() <= 90):
            return None  # projected coordinates - skip
        parts = list(shape.parts) + [len(pts)]
        return [(pts[a:b, 0], pts[a:b, 1]) for a, b in zip(parts[:-1], parts[1:])]
    return None
