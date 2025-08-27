import os
import pandas as pd
import geopandas as gpd
from deepforest import main
from deepforest import preprocess
from shapely.geometry import box
import rasterio


def load_deepforest_model(use_release=True, weights_path=None):
    model = main.deepforest()
    if weights_path:
        model.load_from_checkpoint(weights_path)
    elif use_release:
        model.use_release()
    return model


def detect_on_raster(model, raster_path, patch_size=512, patch_overlap=0.1, score_threshold=0.3):
    """
    Run DeepForest detection on the raster by tiling. Returns GeoDataFrame of detections in raster CRS.
    """
    # DeepForest has utilities to split rasters and run inference on tiles
    # We'll use `preprocess.split_raster` to create tiles in a temporary folder
    import tempfile
    tmpdir = tempfile.mkdtemp()
    # split into tiles: returns pandas DataFrame with tile metadata
    tiles = preprocess.split_raster(raster_path, tmpdir, tile_size=patch_size, overlap=patch_overlap)

    all_preds = []
    for _, t in tiles.iterrows():
        image_path = t["image_path"]
        preds = model.predict_image(path=image_path, return_plot=False)
        if preds is None or preds.empty:
            continue
        # preds are pixel coords relative to the tile. Convert to raster coords
        # tile has offset (xoff,yoff) in pixels in columns 'x_start','y_start' if split_raster supplies them
        x_off = int(t.get("x_start", 0))
        y_off = int(t.get("y_start", 0))
        preds["xmin"] = preds["xmin"] + x_off
        preds["xmax"] = preds["xmax"] + x_off
        preds["ymin"] = preds["ymin"] + y_off
        preds["ymax"] = preds["ymax"] + y_off
        preds["image_path"] = raster_path
        all_preds.append(preds)

    if not all_preds:
        return gpd.GeoDataFrame(columns=["xmin","ymin","xmax","ymax","label","score","geometry"], crs=None)

    df = pd.concat(all_preds, ignore_index=True)

    # Convert pixel bboxes to geometry in raster CRS
    geoms = []
    with rasterio.open(raster_path) as src:
        transform = src.transform
        crs = src.crs
        for _, row in df.iterrows():
            # row has xmin/ymin/xmax/ymax in pixel coords relative to full raster
            minx, miny = rasterio.transform.xy(transform, row["ymin"], row["xmin"]) # careful ordering
            maxx, maxy = rasterio.transform.xy(transform, row["ymax"], row["xmax"])
            geom = box(minx, miny, maxx, maxy)
            geoms.append(geom)
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs=crs)
    return gdf