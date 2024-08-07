from flask import Flask, request, jsonify, send_file, render_template
import os
from werkzeug.utils import secure_filename
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pyproj import CRS
from PIL import Image
from tqdm import tqdm
import zipfile
Image.MAX_IMAGE_PIXELS = None

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

def create_geocoordinate_file(output_file, transform, file_type):
    """Create a .jgw or .tfw file for geospatial coordinates."""
    if file_type in ['jpg', 'jpeg', 'png']:
        world_file = output_file.rsplit('.', 1)[0] + '.jgw'
    elif file_type in ['tif', 'tiff']:
        world_file = output_file.rsplit('.', 1)[0] + '.tfw'
    else:
        raise ValueError("Unsupported file type for geocoordinate file creation")

    with open(world_file, 'w') as f:
        f.write(f"{transform[0]}\n")  # Pixel size in the x-direction in map units/pixel
        f.write(f"{transform[1]}\n")  # Rotation term (typically 0 for non-rotated images)
        f.write(f"{transform[3]}\n")  # Rotation term (typically 0 for non-rotated images)
        f.write(f"{transform[4]}\n")  # Pixel size in the y-direction in map units/pixel (negative for north-up images)
        f.write(f"{transform[2]}\n")  # X coordinate of the center of the upper left pixel
        f.write(f"{transform[5]}\n")  # Y coordinate of the center of the upper left pixel

    print(f"Geocoordinate file created: {world_file}")

def reproject_geotiff(input_file, output_file, epsg_code, file_type):
    # Check file size (limit of 1GB = 1,073,741,824 bytes)
    if os.path.getsize(input_file) > 1073741824:
        raise ValueError("Input file exceeds the 1GB size limit")

    print(f"Image type {file_type} selected. Geocoordinate file created.")
    print('Processing......')

    # Load the source GeoTIFF
    try:
        with rasterio.open(input_file) as src:
            src_crs = CRS(src.crs)
            dst_crs = CRS.from_epsg(epsg_code)

            # Calculate transform and dimensions for the new projection
            transform, width, height = calculate_default_transform(
                src_crs, dst_crs, src.width, src.height, *src.bounds)

            # Define metadata for the new file
            kwargs = src.meta.copy()
            kwargs.update({
                'crs': dst_crs.to_string(),
                'transform': transform,
                'width': width,
                'height': height
            })

            # Reproject and save the new GeoTIFF
            with rasterio.open(output_file, 'w', **kwargs) as dst:
                for band in tqdm(src.indexes, desc='Processing Bands'):
                    # Reproject each band with a progress bar
                    reproject(
                        source=rasterio.band(src, band),
                        destination=rasterio.band(dst, band),
                        src_crs=src_crs,
                        dst_crs=dst_crs,
                        resampling=Resampling.nearest
                    )

            # Handle additional file types
            if file_type in ['jpg', 'jpeg', 'png']:
                # Create geocoordinate file for JPEG/PNG
                create_geocoordinate_file(output_file, transform, file_type)

            print(f"Reprojected file saved as: {output_file}")

    except ValueError as e:
        print(f"Error: {e}")

@app.route('/process-image', methods=['POST'])
def process_image():
    file = request.files.get('file')
    epsg_code = request.form.get('epsgCode')
    output_type = request.form.get('outputType')

    if not file or not epsg_code or not output_type:
        return jsonify({'error': 'Missing data'}), 400

    filename = secure_filename(file.filename)
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(input_path)

    processed_filename = f"{os.path.splitext(filename)[0]}_processed.{output_type}"
    processed_path = os.path.join(app.config['PROCESSED_FOLDER'], processed_filename)

    if output_type in ['jpg', 'jpeg', 'png', 'tif', 'tiff']:
        reproject_geotiff(input_path, processed_path, int(epsg_code), output_type)
    else:
        return jsonify({'error': 'Unsupported output type'}), 400

    # Create a ZIP file containing both the processed image and the world file
    zip_filename = f"EPSG_{epsg_code}_{os.path.splitext(processed_filename)[0]}.zip"
    zip_path = os.path.join(app.config['PROCESSED_FOLDER'], zip_filename)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        zipf.write(processed_path, os.path.basename(processed_path))
        world_file_ext = 'tfw' if output_type.lower() in ['tif', 'tiff'] else 'jgw'
        world_file = f"{os.path.splitext(processed_filename)[0]}.{world_file_ext}"
        world_file_path = os.path.join(app.config['PROCESSED_FOLDER'], world_file)
        if os.path.exists(world_file_path):
            zipf.write(world_file_path, os.path.basename(world_file_path))

    return jsonify({
        'fileUrl': f'/download/{zip_filename}'
    })

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['PROCESSED_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    app.run(debug=True)
