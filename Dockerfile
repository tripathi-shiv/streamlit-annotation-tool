FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive


# System deps for geospatial libs
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential \
libgl1 \
libglib2.0-0 \
gdal-bin libgdal-dev \
libspatialindex-dev \
libgeos-dev \
wget && rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt


COPY . /app/


EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]