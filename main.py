import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pyproj import CRS
from tqdm import tqdm
import os
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

def create_geocoordinate_file(output_file, transform, file_type):
    # Create a .tfw or .jgw file for geocoordinates
    if file_type in ['jpg', 'jpeg']:
        world_file = output_file.rsplit('.', 1)[0] + '.jgw'
    elif file_type == 'png':
        world_file = output_file.rsplit('.', 1)[0] + '.jgw'
    else:
        raise ValueError("Unsupported file type for geocoordinate file creation")

    with open(world_file, 'w') as f:
        # Write the transform values to the .jgw file
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

# Inputs
target_epsg = 3857  # EPSG code for Web Mercator
output_file_name = 'testing_output'
input_geotiff = './input/testing_vert_4326.tif'
output_file_type = 'jpg'  # Can be 'jpg', 'png', or 'tif'

# Auto-generated output file name
output_geotiff = f'./output/{output_file_name}_EPSG_{target_epsg}.{output_file_type}'

# Run function
reproject_geotiff(input_geotiff, output_geotiff, target_epsg, output_file_type)
