# CAMELS-IND Explorer

A simple Streamlit web app for exploring the CAMELS-IND dataset
(472 catchments in Peninsular India, daily data 1980–2020).

## What it does
- **Map of catchments**: every gauge on a map. Colour dots by any attribute and click a dot to select it.
- **One catchment**: hydrograph (rain on top, flow below), flow duration curve, monthly pattern,
  yearly water balance and runoff ratio, data gaps, weather variables, all attributes, and a CSV download.
- **Compare catchments**: up to 8 catchments on the same charts, in mm/day.
- **Attributes**: scatter plots, histograms, box plots and a correlation matrix across catchments.
- Filters in the sidebar: river basin, state, minimum % of observed flow data, or any attribute range.

## Run on your computer
```
pip install -r requirements.txt
streamlit run app.py
```
Then in the sidebar choose **Folder on this computer** and paste the path of your unzipped
CAMELS-IND folder, or set it once:  `set CAMELS_DIR=D:\CAMELS_IND` (Windows) before running.
You can also put the unzipped data in a folder called `data` next to `app.py`.

## Run on the web (Streamlit Community Cloud)
1. Put `app.py`, `camels_loader.py`, `labels.py` and `requirements.txt` in a GitHub repository.
2. On share.streamlit.io, create a new app from that repository with `app.py` as the main file.
3. Open the app and choose **Download from Zenodo** in the sidebar. It downloads the data once
   (about 180 MB for the 242 good-flow catchments) and keeps it while the app is running.

The data files are too big for GitHub, so do **not** upload the data to the repository.

## Speed
- The big streamflow files are converted to a fast format (Parquet) the first time, so later starts take under a second.
- Only the chart you pick is drawn, and switching charts does not reload the page.
- Long daily series use WebGL drawing, so zooming through 41 years of daily data stays smooth.

## Files
| File | What it is |
|---|---|
| app.py | The web app (pages, charts, sidebar) |
| camels_loader.py | Finds and reads the CAMELS-IND files automatically |
| labels.py | Turns column names like `high_prec_freq` into plain English |
| .streamlit/config.toml | Colours and theme of the app |

Data: Mangukiya et al. (2025), CAMELS-IND, *Earth System Science Data* 17, 461–491,
https://doi.org/10.5194/essd-17-461-2025 – Zenodo record 14999580.
