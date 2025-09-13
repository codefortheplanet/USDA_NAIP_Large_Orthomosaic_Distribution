# USDA NAIP Large Orthomosaic Distribution

This is an automated workflow for the distribution of 2022 USDA National Agriculture Imagery Program (NAIP) aerial imagery (30 - 60 cm resolution, depending on the state) at the county level or for customized AOI. A pre-compiled GDAL wheel is provided for processing the MrSID raster files. Unlike common distribution platforms, such as NASA's Earth Explorer, users can directly retrieve large-scale (county-level or equivalent-scale AOI) NAIP orthomosaic data without post-processing a large number of small tiles. 

Note that, due to resource limitations, I have only created a complete workflow for California; however, the same workflow can be applied to any CONUS U.S. state. 

## Usage
Three simple steps:

(1) Download the GDAL wheel and use pip to install it in a virtual environment (such as virtualenv or Conda) with Python=3.11. This wheel includes all scripts, shared library files, and format drivers, including MrSID and File Geodatabase (read-only) for GDAL version 3.11.3.  
```
pip install GDAL-3.11.3-cp311-cp311-manylinux_2_35_x86_64.whl
```
Install other required packages
```
pip install -r requirements.txt
```
Install PROJ binary (yes, this one is special)
```
sudo apt-get install proj-bin
```

(2) Clone the repo. Three files are placed in the 'data' directory: 

merged_dissolved_geopackage.gpkg includes three pre-built vector layers (polygon geometries) outlining the NAIP ortho boundaries. The layer with Geographic Coordinate System NAD83 (unprojected to local UTM) will be used as the spatial query index file for retrieving corresponding zip(s) from the USDA NAIP data repository on Box (other layers are in local UTM projection); 

tlgpkg_db_2025_a_06_ca.gpkg includes U.S. Census Tiger Data for county boundaries; 

compiled_ortho_link.csv includes the ortho zip file names and the Box URLs lookup table for pulling the token and downloading these zip files. 

Note that due to the file size restriction, please download the tlgpkg_db_2025_a_06_ca.gpkg directly from the U.S. Census site at https://www2.census.gov/geo/tiger/TGRGPKG25/tlgpkg_db_2025_a_06_ca.gpkg.zip and unzip the gpkg file directly (without any parent directory) in the 'data' directory.

(3) The last step is to run extract_mrsid.py for the interested county or an AOI (as a shapefile):

```
python extract_mrsid.py --county=Sacramento 
```
or
```
python extract_mrsid.py --aoi=aoi.shp
```
If you use the AOI shapefile, please place it under 'data' directory.

The selected county or cropped raster GeoTiff will be saved in the 'naip_out' directory.

### Note
Because of the large file size, I use the parallel processing module in the orthomosaicking and cropping steps to run simultaneously on multiple CPU cores. 
Additionally, for those interested in learning more about the workflow for generating the merged_dissolved_geopackage.gpkg and compiled_ortho_link.csv, I have included a detailed description of how to use two additional scripts to generate these files for any other CONUS U.S. states. 