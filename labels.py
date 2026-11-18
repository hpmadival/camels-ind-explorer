"""Plain-English names for CAMELS-IND column names (no underscores on screen)."""

import re

KNOWN = {
    # location
    "cwc_lat": "Gauge latitude", "cwc_lon": "Gauge longitude",
    "cwc_site_name": "Gauge site name", "cwc_river": "River", "cwc_basin": "River basin",
    "cwc_state": "State", "cwc_area": "Catchment area (CWC, km²)", "ghi_area": "Catchment area (GHI, km²)",
    "ghi_lat": "Gauge latitude (GHI)", "ghi_lon": "Gauge longitude (GHI)",
    "flow_availability": "Streamflow data available (%)",
    # topography
    "elev_mean": "Mean elevation (m)", "elev_min": "Lowest elevation (m)", "elev_max": "Highest elevation (m)",
    "elev_median": "Median elevation (m)", "slope_mean": "Mean slope", "dpsbar": "Mean drainage path slope",
    # climate
    "p_mean": "Mean daily rainfall (mm/day)", "pet_mean": "Mean daily potential evaporation (mm/day)",
    "aet_mean": "Mean daily actual evaporation (mm/day)",
    "aridity": "Aridity index (PET ÷ P)", "p_seasonality": "Rainfall seasonality",
    "frac_snow": "Fraction of rain falling as snow", "high_prec_freq": "Days with heavy rain (days/yr)",
    "high_prec_dur": "Length of heavy-rain spells (days)", "high_prec_timing": "Season of heavy rain",
    "low_prec_freq": "Dry days (days/yr)", "low_prec_dur": "Length of dry spells (days)",
    "low_prec_timing": "Season of dry days", "t_mean": "Mean air temperature (°C)",
    # hydrology
    "q_mean": "Mean daily flow (mm/day)", "runoff_ratio": "Runoff ratio (Q ÷ P)",
    "stream_elas": "Streamflow elasticity to rain", "slope_fdc": "Slope of flow duration curve",
    "baseflow_index": "Baseflow index", "bfi": "Baseflow index", "hfd_mean": "Half-flow date (day of year)",
    "q5": "Low flow, Q5 (mm/day)", "q95": "High flow, Q95 (mm/day)",
    "high_q_freq": "High-flow days (days/yr)", "high_q_dur": "Length of high-flow spells (days)",
    "low_q_freq": "Low-flow days (days/yr)", "low_q_dur": "Length of low-flow spells (days)",
    "zero_q_freq": "Fraction of zero-flow days",
    # land, soil, geology
    "dom_land_cover": "Main land cover", "dom_land_cover_frac": "Share of main land cover",
    "forest_frac": "Forest share", "crop_frac": "Cropland share", "urban_frac": "Urban share",
    "water_frac": "Water share", "lai_max": "Peak leaf area index", "gvf_max": "Peak green vegetation",
    "soil_depth": "Soil depth (m)", "soil_porosity": "Soil porosity", "soil_conductivity": "Soil conductivity",
    "max_water_content": "Soil water holding capacity", "sand_frac": "Sand share (%)",
    "silt_frac": "Silt share (%)", "clay_frac": "Clay share (%)",
    "geol_class_1st": "Main rock type", "geol_class_1st_frac": "Share of main rock type",
    "geol_porosity": "Rock porosity", "geol_permeability": "Rock permeability",
    "carbonate_rocks_frac": "Carbonate rock share",
    # human influence
    "dam_count": "Number of dams", "num_dams": "Number of dams", "pop_density": "Population density (per km²)",
    "total_vol": "Total dam storage", "degree_of_regulation": "Degree of regulation",
}

WORDS = {
    "p": "rainfall", "q": "flow", "pet": "potential evaporation", "aet": "actual evaporation",
    "prcp": "rainfall", "tmax": "maximum temperature", "tmin": "minimum temperature",
    "tavg": "mean temperature", "frac": "share", "freq": "frequency", "dur": "duration",
    "elev": "elevation", "dom": "main", "num": "number of", "lai": "leaf area index",
    "gvf": "green vegetation", "cwc": "CWC", "ghi": "GHI", "rh": "relative humidity",
    "srad": "solar radiation", "lrad": "long-wave radiation", "wind": "wind speed",
    "sm": "soil moisture", "gleam": "(GLEAM)", "imd": "(IMD)", "lstm": "LSTM",
    "lvl1": "level 1", "lvl2": "level 2", "cv": "variation",
}

FORCING_KNOWN = {
    "prcp": "Rainfall", "prcp(mm/day)": "Rainfall (mm/day)", "tmax": "Maximum temperature",
    "tmin": "Minimum temperature", "tavg": "Mean temperature", "srad_lw": "Long-wave radiation",
    "srad_sw": "Short-wave radiation", "wind": "Wind speed", "rel_hum": "Relative humidity",
    "pet": "Potential evaporation", "aet": "Actual evaporation",
}


def nice(col: str) -> str:
    """'high_prec_freq' -> 'Days with heavy rain (days/yr)'; unknown -> 'Words with spaces'."""
    if col is None:
        return ""
    raw = str(col).strip()
    key = raw.lower()
    if key in KNOWN:
        return KNOWN[key]
    if key in FORCING_KNOWN:
        return FORCING_KNOWN[key]
    unit = ""
    m = re.search(r"\(([^)]*)\)\s*$", raw)
    if m:
        unit = f" ({m.group(1)})"
        key = key[: m.start()].strip()
        if key in FORCING_KNOWN:
            return FORCING_KNOWN[key] + unit
    parts = [WORDS.get(w, w) for w in re.split(r"[_\s]+", key) if w]
    text = " ".join(parts).strip()
    return (text[:1].upper() + text[1:] + unit) if text else raw
