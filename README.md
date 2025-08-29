# 🌳 Tree Annotation Tool

A web-based application for automated tree detection and manual annotation using satellite imagery. This tool combines deep learning-based tree detection with interactive manual annotation capabilities to create comprehensive tree datasets.

## 🚀 Features

- **Automated Tree Detection**: Uses DeepForest model to automatically detect trees in satellite imagery
- **Interactive Annotation**: Manual drawing tools for additional tree annotations
- **KML/KMZ Support**: Upload geographic boundaries via KML/KMZ files
- **High-Resolution Satellite Imagery**: Downloads high-zoom satellite imagery for detailed analysis
- **Cloud Storage Integration**: Automatic upload to AWS S3 for image and annotation storage
- **Export Capabilities**: Save annotations as CSV files with geographic coordinates
- **Web-Based Interface**: Built with Streamlit for easy access and use

## 🛠️ Technology Stack

- **Frontend**: Streamlit, Folium (interactive maps)
- **AI/ML**: DeepForest (tree detection model)
- **Geospatial**: GeoPandas, Rasterio, Shapely
- **Cloud**: AWS S3 (storage)
- **Satellite Imagery**: TMS/XYZ tile services
- **Containerization**: Docker

## 📋 Prerequisites

- Python 3.11+
- AWS S3 bucket and credentials
- Docker (optional, for containerized deployment)

## 🚀 Quick Start

1. **Build the Docker image**
   ```bash
   docker build -t annotation-tool .
   ```

2. **Run the container**
   ```bash
   docker run -it --rm \
     -v $(pwd):/app \
     -p 8501:8501 \
     --env-file .env \
     annotation-tool
   ```

## 📖 Usage Guide

### 1. Upload KML/KMZ File
- Upload a KML or KMZ file containing the geographic boundary of the area you want to analyze
- The tool will automatically download high-resolution satellite imagery for that area

### 2. Automatic Tree Detection
- The DeepForest model will automatically detect trees in the satellite imagery
- Detected trees are filtered by:
  - Area: ≤ 60 m² (to exclude large objects)
  - Confidence score: ≥ 0.15 (to ensure quality detections)

### 3. Manual Annotation
- Use the drawing tools on the map to add additional tree annotations
- Draw rectangles around trees that may have been missed by the model
- All manually drawn annotations are labeled as "Tree"

### 4. Save Annotations
- Click "Save Annotations as CSV" to export all annotations
- The CSV file includes:
  - Geographic coordinates (WGS84)
  - Pixel coordinates
  - Tree areas
  - Confidence scores
  - Source (model vs. manual annotation)
  - Image path reference

### 5. Download Results
- Download the CSV file locally
- Annotations are also automatically uploaded to your S3 bucket

## 📁 Project Structure

```
annotation-tool/
├── app.py                 # Main Streamlit application
├── utils.py              # Utility functions for geospatial operations
├── model-inference.py    # DeepForest model inference utilities
├── requirements.txt      # Python dependencies
├── Dockerfile           # Docker configuration
├── .streamlit/          # Streamlit configuration
│   └── secrets.toml     # AWS credentials (create this)
└── venv/                # Virtual environment (created locally)
```

## 🔧 Configuration

### Model Configuration
The DeepForest model uses default settings optimized for tree detection:
- Minimum confidence threshold: 0.15
- Maximum tree area: 60 m²
- Satellite imagery zoom level: 19

## 📊 Output Format

The tool generates CSV files with the following columns:
- `geometry`: Geographic coordinates (WGS84)
- `xmin`, `ymin`, `xmax`, `ymax`: Pixel coordinates
- `label`: Tree classification
- `score`: Detection confidence (model predictions only)
- `area_m2`: Tree crown area in square meters
- `labelled_by`: Source of annotation ("model" or "user")
- `image_path`: Reference to the satellite image

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [DeepForest](https://github.com/weecology/DeepForest) - Tree detection model
- [Streamlit](https://streamlit.io/) - Web application framework
- [GeoPandas](https://geopandas.org/) - Geospatial data manipulation
- [Folium](https://python-visualization.github.io/folium/) - Interactive maps

## 🐛 Troubleshooting

### Common Issues

1. **GDAL Installation Issues**
   - On macOS: `brew install gdal`
   - On Ubuntu: `sudo apt-get install libgdal-dev`
   - Use conda: `conda install gdal`

2. **AWS Credentials Not Found**
   - Ensure `.streamlit/secrets.toml` exists and contains valid credentials
   - Check AWS IAM permissions for S3 access

3. **Memory Issues with Large Images**
   - Reduce the area size in your KML file
   - The tool automatically ensures a minimum area of 9,500 m²

4. **No Trees Detected**
   - Check if the satellite imagery is clear and contains trees
   - Verify the area is not too small or too large
   - Try adjusting the confidence threshold in the code
