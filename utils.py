import rasterio
from rasterio.transform import rowcol
from rasterio.transform import Affine
from shapely.geometry import box, shape, mapping
import geopandas as gpd
import pandas as pd
import numpy as np
import rioxarray
from shapely.geometry import Polygon
from samgeo import tms_to_geotiff
import os
import streamlit as st
from botocore.exceptions import NoCredentialsError, ClientError
import boto3

s3_client = None

def configure_aws_credentials(aws_access_key_id=None, aws_bucket_name=None, aws_secret_access_key=None, aws_region=None):
    global s3_client
    if aws_access_key_id and aws_bucket_name and aws_secret_access_key:
        s3_client = boto3.client('s3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        return s3_client
    else:
        return None



def download_from_s3(s3_key, local_path):
    global s3_client
    try:
        bucket_name = st.secrets["bucket_name"]
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3_client.download_file(bucket_name, s3_key, local_path)
        print(f"Successfully downloaded {s3_key} to {local_path}")
        return True
        
    except NoCredentialsError:
        print("AWS credentials not found. Please configure your AWS credentials.")
        return False
    except ClientError as e:
        print(f"Error downloading file: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


def upload_to_s3(local_path, s3_key):
    global s3_client
    try:
        bucket_name = st.secrets["bucket_name"]
        # Check if file exists locally
        if not os.path.exists(local_path):
            st.error(f"Local file {local_path} does not exist")
            return None
        
        # Upload the file
        with open(local_path, "rb") as f:
            s3_client.put_object(Bucket=bucket_name.replace(" ", ""), Key=s3_key, Body=f, ACL='public-read')


        # Return the S3 URL (https)
        s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"

        return s3_url
        
    except NoCredentialsError:
        st.error("AWS credentials not found. Please configure your AWS credentials.")
        return None
    except ClientError as e:
        st.error(f"Error uploading file: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None



def download_kml_and_tiff(image_path):
    raster = rioxarray.open_rasterio(image_path)
    return raster

def get_tree_crowns(gdf, image, model):
    image.shape
    image_transpo = image.transpose('x','y','band')

    if sum([len(x) for x in np.where(image != 0)]) > 0:

        pred_boxes = model.predict_image(image=image_transpo.values)

        if isinstance(pred_boxes, pd.DataFrame) and pred_boxes is not None:

            pred_boxes['new_geometry'] = None
            pred_boxes['new_geometry'] = pred_boxes.geometry.apply(lambda coord:Polygon([(image_transpo[int(y)-1,int(x)-1,:].coords['x'].values.item(),image_transpo[int(y)-1,int(x)-1,:].coords['y'].values.item()) for x,y in list(coord.exterior.coords)]))
            pred_boxes_new = pred_boxes.copy()
            pred_boxes_new = pred_boxes_new.drop('geometry', axis=1).rename(columns= {'new_geometry':'geometry'})


            # Google Images Projection - 3857
            pred_boxes_new.set_crs(crs = 3857, inplace=True)
            pred_boxes_new = pred_boxes_new.to_crs(crs = 4326)
            confidence_factor = pred_boxes_new.copy()

            conf_preds_for_crs = pred_boxes_new.to_crs("EPSG:3857")
            conf_preds_for_crs['area_m2'] = conf_preds_for_crs.geometry.area

            sel_forest_calss = conf_preds_for_crs.copy()
            return sel_forest_calss
        else:
            return None
    else:
        return None

def get_image_size(tif_path):
    with rasterio.open(tif_path) as src:
        return src.width, src.height

def pixel_to_geo(transform, col, row):
    x, y = rasterio.transform.xy(transform, row, col)
    return x, y


def bbox_pixel_to_geom(transform, xmin, ymin, xmax, ymax, src_crs):
    # xmin,xmax are column indices, ymin,ymax are row indices (pixel coords)
    # convert to geocoords using raster transform
    # note: rowcol/xy coordinate ordering must be handled carefully
    x_min, y_max = rasterio.transform.xy(transform, ymin, xmin)  # top-left? verify ordering
    x_max, y_min = rasterio.transform.xy(transform, ymax, xmax)
    # safer approach: use rasterio.transform.xy with (row, col)
    # But instead we use transform * (col+0.5, row+0.5)
    a = transform
    # compute geocoords for corners
    x_min, y_min = a * (xmin, ymin)
    x_max, y_max = a * (xmax, ymax)
    return box(x_min, y_min, x_max, y_max)

def ensure_min_area(kml_path, min_area=9500, epsg_projected=32644):
    # Read and reproject to projected CRS for area calculation
    gdf = gpd.read_file(kml_path, driver="KML")
    gdf = gdf.to_crs(epsg=epsg_projected)

    # Compute current area
    current_area = gdf.geometry.area.sum()

    if current_area < min_area:
        # Estimate required buffer radius (approximate)
        deficit = min_area - current_area
        buffer_dist = (deficit / current_area) ** 0.5 * 10  # heuristic scaling

        # Apply buffer iteratively until area ≥ min_area
        while gdf.geometry.area.sum() < min_area:
            gdf["geometry"] = gdf.buffer(buffer_dist)
            buffer_dist *= 1.1  # increase buffer if still not enough

    # Convert back to WGS84
    gdf = gdf.to_crs(epsg=4326)
    return gdf

def geoms_to_pixel_bbox(gdf, raster_path):
    """
    Overwrite gdf xmin,ymin,xmax,ymax by converting geometry bounds into pixel coords
    using the raster transform. Returns a new GeoDataFrame with pixel bbox columns.
    """

    with rasterio.open(raster_path) as src:
        transform = src.transform
        width = src.width
        height = src.height
        xmins, ymins, xmaxs, ymaxs = [], [], [], []
        for geom in gdf.geometry:
            minx, miny, maxx, maxy = geom.bounds
            # convert map coords -> row/col
            row_min, col_min = rowcol(transform, minx, maxy)  # careful ordering
            row_max, col_max = rowcol(transform, maxx, miny)
            # clip to image bounds
            xmin = np.clip(col_min, 0, width - 1)
            ymin = np.clip(row_min, 0, height - 1)
            xmax = np.clip(col_max, 0, width - 1)
            ymax = np.clip(row_max, 0, height - 1)
            xmins.append(xmin)
            ymins.append(ymin)
            xmaxs.append(xmax)
            ymaxs.append(ymax)
        out = gdf.copy()
        out["xmin"] = xmins
        out["ymin"] = ymins
        out["xmax"] = xmaxs
        out["ymax"] = ymaxs
        return out

def user_rois_to_bbox(user_rois, target_crs="EPSG:3857", label="Tree", raster_path=None):

    if user_rois["type"] == "FeatureCollection":
        features = user_rois["features"]
    else:
        features = [user_rois]

    user_gdf = gpd.GeoDataFrame(
        [feat.get("properties", {}) for feat in features],
        geometry=[shape(feat["geometry"]) for feat in features],
        crs="EPSG:4326"
    )

    user_gdf = user_gdf.to_crs(target_crs)

    user_gdf["xmin"] = user_gdf.bounds.minx
    user_gdf["ymin"] = user_gdf.bounds.miny
    user_gdf["xmax"] = user_gdf.bounds.maxx
    user_gdf["ymax"] = user_gdf.bounds.maxy

    user_gdf["label"] = label
    user_gdf["score"] = None 
    user_gdf["area_m2"] = user_gdf.geometry.area

    cols = ["xmin", "ymin", "xmax", "ymax", "label", "score", "geometry", "area_m2"]
    return geoms_to_pixel_bbox(user_gdf, raster_path)

