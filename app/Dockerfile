# my_app/app/Dockerfile

FROM python:3.9-slim

# Install system dependencies needed by GeoPandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy in requirements first (for Docker build cache efficiency)
COPY ./app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app code
COPY . .

EXPOSE 8501

# Default command to run Streamlit on container start
CMD ["streamlit", "run", "./app/main_0.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
