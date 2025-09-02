import os
import tempfile
import geopandas as gpd
import pandas as pd
import streamlit as st
import leafmap.foliumap as leafmap
import re
from deepforest import main as deepforest_main
from utils import tms_to_geotiff
from utils import get_tree_crowns
from utils import download_kml_and_tiff
from utils import upload_to_s3
from utils import user_rois_to_bbox
from utils import configure_aws_credentials
from utils import ensure_min_area
from streamlit_folium import st_folium
from folium.plugins import Draw
import json
# -----------------------------
# Load DeepForest pretrained model
# -----------------------------
@st.cache_resource
def load_model():
    model = deepforest_main.deepforest()
    model.use_release()
    return model

# -----------------------------
# Convert DeepForest detections to GeoDataFrame
# -----------------------------
def detections_to_gdf(detections, crs="EPSG:4326"):
    if detections.empty:
        return gpd.GeoDataFrame(columns=["geometry", "label"], crs=crs)

    gdf = gpd.GeoDataFrame(
        detections,
        geometry=gpd.points_from_xy(detections.xcenter, detections.ycenter),
        crs=crs,
    )
    gdf["label"] = "Tree"
    return gdf


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(layout="wide")
st.title("🌳 Tree Annotation Tool")

model = load_model()
source = "SATELLITE"


def setup_aws_credentials():
    aws_access_key_id = st.secrets["access_key_id"]
    aws_secret_access_key = st.secrets["secret_access_key"]
    aws_bucket_name = st.secrets["bucket_name"]
    aws_region = st.secrets["region"]
    configure_aws_credentials(aws_access_key_id, aws_bucket_name, aws_secret_access_key, aws_region)


# File upload
uploaded_file = st.file_uploader("Upload a KML/KMZ file", type=["kml", "kmz"])
if uploaded_file:
    # Save to a temp file
    setup_aws_credentials()
    kml_filename = os.path.splitext(os.path.basename(uploaded_file.name))[0]
    kml_filename = re.sub(r'[^A-Za-z0-9_-]', '_', kml_filename)
    osm_download = f"{kml_filename}.tif"

    s3_key = f"satellite-images/{osm_download}"

    # Ensure minimum area of the polygon
    gdf = ensure_min_area(uploaded_file, min_area=9500)
    minx, miny, maxx, maxy = gdf.total_bounds
    
    tms_to_geotiff(osm_download, bbox=[minx, miny, maxx, maxy], zoom=19, source=source, overwrite=True)
    uploaded_url = upload_to_s3(osm_download, s3_key)
    image = download_kml_and_tiff(osm_download)

    concaT_df = get_tree_crowns(gdf, image, model)

    
    # ---- 1) Persistent state for boxes (GeoJSON Features) ----
    if "boxes" not in st.session_state:
        st.session_state.boxes = []           # list of GeoJSON Feature objects
    if "box_keys" not in st.session_state:
        st.session_state.box_keys = set()     # quick dedupe


    # Initialize map
    # Get the centroid of the uploaded KML geometry for map centering
    centroid = gdf.geometry.centroid.iloc[0]
    m = leafmap.Map(center=[centroid.y, centroid.x],draw_control=False, zoom_to_layer=False, zoom=19)
    m.add_basemap('SATELLITE', layers_control=True)
    # m.add_basemap("Hybrid")  # Satellite imagery
    style = {
        "color": "#ff0000",
        "weight": 2,
        "fillOpacity": 0,
    }

    if st.session_state.boxes:
        m.add_geojson(
            {"type": "FeatureCollection", "features": st.session_state.boxes},
            layer_name="Saved boxes",
        )

    if uploaded_url:
        m.add_cog_layer(url=uploaded_url, name="Satellite",zoom_to_layer=False)
    else:
        st.error(f"❌ Raster file not found: {uploaded_url}")
        
    if concaT_df.empty:
        st.error("No trees found in the image")
        m.to_streamlit()
    else:
        geome = concaT_df[(concaT_df.area_m2<=60) & (concaT_df.score>=0.15)].reset_index(drop=True)
        if not geome.empty:
            m.add_gdf(geome, layer_name="Predicted Trees")
        else: 
            st.error("No trees found in the image")
          
        st.write("Draw additional boxes (all will be labeled as 'Tree'):")
        # Display map
        filename = f'user-rois_{kml_filename}.geojson'
        draw = Draw(
            export=True,
            filename=filename,
            position='topleft',
            draw_options={
                'polyline': False,
                'circle': False,
                'circlemarker': False,
            },
            edit_options={'edit': True}
        )
        draw.add_to(m)
        out = m.to_streamlit(height=750, key="main_map")
        new_feat = None
        if isinstance(out, dict):
            new_feat = out.get("last_active_drawing") or out.get("last_drawing")

        if new_feat:
            s = json.dumps(new_feat, sort_keys=True)
            if s not in st.session_state.box_keys:
                st.session_state.boxes.append(new_feat)
                st.session_state.box_keys.add(s)


        uploaded_rois = st.file_uploader("Upload user ROIs", type=["geojson"])
        drawn_features = None

        if uploaded_rois:
            try:
                drawn_features = json.load(uploaded_rois)
                st.success("ROIs loaded successfully")
            except Exception as e:
                st.error(f"Error loading ROIs file: {e}")
        

        # Save button
        if drawn_features is not None:
            if st.button("💾 Save Annotations as CSV"):
                gdf_drawn = user_rois_to_bbox(drawn_features, target_crs="EPSG:3857", label="Tree", raster_path=osm_download)
                gdf_drawn['labelled_by'] = "user"
                geome['labelled_by'] = "model"
                # Merge predictions + user annotations
                final_gdf = pd.concat([geome, gdf_drawn], ignore_index=True)
                final_gdf["image_path"] = s3_key
                csv_path = kml_filename.split(".")[0]+"-annotations.csv"
                final_gdf.to_csv(csv_path, index=False)
                csv_s3_key = f"annotations/{csv_path}"
                upload_to_s3(csv_path, csv_s3_key)
                st.success("Annotations uploaded successfully")
                st.download_button(
                    label="⬇️ Download CSV",
                    data=open(csv_path, "rb").read(),
                    file_name=csv_path,
                    mime="text/csv",
                )
                

