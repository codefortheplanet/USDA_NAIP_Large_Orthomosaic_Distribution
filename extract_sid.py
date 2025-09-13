from osgeo import ogr, gdal
import os, re
from zipfile import ZipFile
import pandas as pd
import geopandas as gpd
from manual_grab import *
import subprocess
from multiprocessing import Process
import argparse

os.environ['GDAL_CACHEMAX'] = '25000'

def unzip(zip_ortho, out_raster_path):
    patterns = r"\.sid$"
    with ZipFile(os.path.join(out_raster_path,zip_ortho), 'r') as zipObj:
        # Get a list of all archived file names from the zip
        listOfFileNames = zipObj.namelist()
        print (listOfFileNames)
        # Iterate over the file names
        for fileName in listOfFileNames:
            #check the including file condition.
            match = re.search(patterns,fileName)
            print (match)
            if match is not None:
                print (fileName)
                zipObj.extract(fileName, out_raster_path)
                sid_file = os.path.join(out_raster_path,fileName)
                # tif_file = os.path.join(out_raster_path,fileName.split('.sid')[0] + '.tif')
                # # Convert SID to GeoTIFF
                # gdal.Translate(tif_file, sid_file, format='GTiff')
    return sid_file

def translate(input_inx, input_hc_file, input_hn_files):
    tif_file_hc = os.path.join(out_raster_path, os.path.basename(input_hc_file).split('.sid')[0] + '.tif')
    tif_file_hn = os.path.join(out_raster_path, os.path.basename(input_hn_files[input_inx]).split('.sid')[0] + '.tif')
    translate_options = gdal.TranslateOptions(format='GTiff',
                                              creationOptions=['TFW=YES', 'COMPRESS=LZW','BIGTIFF=YES']
                                             )
    gdal.Translate(tif_file_hc, input_hc_file, options=translate_options)
    print(f'Done converting {input_hc_file} into {tif_file_hc}')
    gdal.Translate(tif_file_hn, input_hn_files[input_inx], options=translate_options)
    print(f'Done converting {input_hn_files[input_inx]} into {tif_file_hn}')

def clip(input_inx, input_vrt, root_path, warp_options, raster_proj):
    out_raster_path = os.path.join(root_path, 'naip_out')
    crop_shp = os.path.join(root_path,'data', 'roi.shp')
    target_crs = gpd.GeoSeries().set_crs(raster_proj).crs

    # Read the shapefile using GeoPandas
    gdf = gpd.read_file(crop_shp)
    # Reproject the GeoDataFrame to the target CRS
    gdf_reprojected = gdf.to_crs(target_crs)
    # Save the reprojected GeoDataFrame to a new shapefile
    proj_aoi = os.path.join(root_path,'data', 'roi_proj.shp')
    gdf_reprojected.to_file(proj_aoi)

    crop_files = ['crop_hc.tif','crop_hn.tif']
    #for inx, input_crop in enumerate([hc_tiles_vrt, hn_tiles_vrt])
    # Clip raster by polygon
    out_tif = crop_files[input_inx]
    gdal.Warp(
        os.path.join(out_raster_path, out_tif),  # Output file
        input_vrt,  # Input raster
        cutlineDSName=proj_aoi,  # Polygon shapefile
        cropToCutline=True,  # Crop raster extent to polygon
        dstNodata=-9999,  # Nodata value for outside polygon
        options=warp_options
    )

#Determine the input and query the pre-built geopackage for intersected counties
#Place the input geopackages and aoi shapefile to the data directory under the processing root directory
#ROI needs to be in NAD83 coordinate system
def query(root_dir, input_roi, county=None):
    if county is None:
        driver = ogr.GetDriverByName('ESRI Shapefile')
        aoi = os.path.join(root_dir, 'data', input_roi)
        data_source = driver.Open(aoi, 0)
        layer = data_source.GetLayer(0)
    else:
        cal_tiger = os.path.join(root_dir, 'data', 'tlgpkg_db_2025_a_06_ca.gpkg')
        driver = ogr.GetDriverByName('GPKG')
        data_source = driver.Open(cal_tiger, 0)
        layer = data_source.GetLayer(1)

    naip_bound = os.path.join(root_dir, 'data', 'merged_dissolved_geopackage.gpkg')
    driver = ogr.GetDriverByName('GPKG')
    data_source_n = driver.Open(naip_bound, 0)
    layer_n = data_source_n.GetLayer(1)

    # Copy features into a temporary in-memory datasource for fast query
    mem_driver = ogr.GetDriverByName("MEM")
    mem_ds = mem_driver.CreateDataSource("")
    mem_ds.CopyLayer(layer, "layer2")
    mem_ds.CopyLayer(layer_n, "layer1")

    if county is None:
        sql_query = f'''
            SELECT a.*
            FROM "layer1" AS a, "layer2" AS b 
            WHERE ST_Intersects(a.geometry, b.geometry);
        '''
    else:
        sql_query = f'''
        SELECT a.*
        FROM "layer1" AS a, "layer2" AS b 
        WHERE ST_Covers(a.geometry, b.geometry) 
        AND b."NAMELSAD" = "{county} County";
    '''

    result_layer = mem_ds.ExecuteSQL(sql_query, dialect="SQLITE")
    feature_count = result_layer.GetFeatureCount()
    return mem_ds, result_layer, feature_count

#Download county level zip files from USDA Box based on the query and unzip MrSID files
def download_unzip(result_layer, feature_count, root_dir):
    out_raster_path = os.path.join(root_dir, 'naip_out')
    lookup_table = os.path.join(root_dir, 'data', 'compiled_ortho_link.csv')
    zip_files = []
    for i in range(feature_count):
        zip_file_c = result_layer[i].GetField("OrthoName_c")
        zip_file_n = result_layer[i].GetField("OrthoName_n")
        zip_files.append([zip_file_c, zip_file_n])
    print('zip files',zip_files)
    urls = []
    # check the url from the pre-built table and download the zip files to disk
    lookup_df = pd.read_csv(lookup_table)
    for zip_f in zip_files:
        zip_c = lookup_df[lookup_df['ORTHO_c'] == zip_f[0]]['URL_c'].reset_index()
        zip_n = lookup_df[lookup_df['ORTHO_n'] == zip_f[1]]['URL_n'].reset_index()
        download_file_from_box(zip_c.iloc[0]['URL_c'], os.path.join(out_raster_path, zip_f[0]))
        download_file_from_box(zip_n.iloc[0]['URL_n'], os.path.join(out_raster_path, zip_f[1]))
        urls.append([zip_c, zip_n])

    sid_files = []
    for zip_ortho in zip_files:
        sid_file_hc = unzip(zip_ortho[0], out_raster_path)
        sid_file_hn = unzip(zip_ortho[1], out_raster_path)
        sid_files.append([sid_file_hc, sid_file_hn])
        os.remove(os.path.join(out_raster_path,zip_ortho[0]))
        os.remove(os.path.join(out_raster_path,zip_ortho[1]))
    print(f'NAIP data search complete and unpacked!')
    return sid_files

def convert_geotiff(sid_files, root_dir, county=None):
    out_raster_path = os.path.join(root_dir, 'naip_out')
    if county is not None:
        tif_file_hc = os.path.join(out_raster_path, os.path.basename(sid_files[0][0]).split('.sid')[0] + '.tif')
        tif_file_hn = os.path.join(out_raster_path, os.path.basename(sid_files[0][1]).split('.sid')[0] + '.tif')
        gdal.Translate(tif_file_hc, sid_files[0][0], format='GTiff')
        gdal.Translate(tif_file_hn, sid_files[0][1], format='GTiff')
        print(f'NAIP data processing complete! Save the cropped GeoTIFF in {out_raster_path}')
    else:
        # #pull the hc and hn tiles, and stitch together
        hc_tiles = [os.path.join(out_raster_path, sid_ortho[0]) for sid_ortho in sid_files]
        hn_tiles = [os.path.join(out_raster_path, sid_ortho[1]) for sid_ortho in sid_files]
        processes = [Process(target=translate, args=(inx, hc_tile, hn_tiles)) for inx, hc_tile in enumerate(hc_tiles)]
        # start all processes
        for process in processes:
            process.start()
        # wait for all processes to complete
        for process in processes:
            process.join()
        # report that all tasks are completed
        print('Done converting all MrSID to GeoTIFF', flush=True)

        hc_tiles_tif = [os.path.join(out_raster_path, os.path.basename(hc_tile).split('.sid')[0] + '.tif') for hc_tile
                        in hc_tiles]
        hn_tiles_tif = [os.path.join(out_raster_path, os.path.basename(hn_tile).split('.sid')[0] + '.tif') for hn_tile
                        in hn_tiles]

        hc_tiles_vrt = os.path.join(out_raster_path, 'merged_hc.vrt')
        hn_tiles_vrt = os.path.join(out_raster_path, 'merged_hn.vrt')
        gdal.BuildVRT(hc_tiles_vrt, hc_tiles_tif)
        gdal.BuildVRT(hn_tiles_vrt, hn_tiles_tif)

        warp_options = gdal.WarpOptions(
            format='GTiff',
            multithread=True,
            creationOptions=['TILED=YES', 'COMPRESS=LZW', 'BIGTIFF=YES'],
            resampleAlg='near'
        )

        dataset = gdal.Open(hc_tiles_vrt)
        if dataset is None:
            print("Failed to open the raster file.")
            return None
        # Get the projection information
        projection = dataset.GetProjection()
        dataset = None
        processes = [Process(target=clip, args=(inx, vrt_tile, root_dir, warp_options, projection)) for inx, vrt_tile in
                     enumerate([hc_tiles_vrt, hn_tiles_vrt])]
        # start all processes
        for process in processes:
            process.start()
        # wait for all processes to complete
        for process in processes:
            process.join()
        # report that all tasks are completed
        print(f'NAIP data processing complete! Save the result GeoTIFF in {out_raster_path}')

        for inx, hc_tile in enumerate(hc_tiles):
            os.remove(hc_tile)
            os.remove(hn_tiles[inx])
            os.remove(hc_tiles_tif[inx])
            os.remove(hn_tiles_tif[inx])
        os.remove(hc_tiles_vrt)
        os.remove(hn_tiles_vrt)

def parser():
    parser = argparse.ArgumentParser(description="User input for county name or AOI (exclusive)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-c', '--county', type=str, default=None, help="Input county name, with out the word 'county' at the end")
    group.add_argument('-a', '--aoi', type=str, default=None, help="Input area of interest (AOI) in a shapefile: .shp")
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    county = parser().county
    aoi = parser().aoi
    root_dir = os.path.dirname(os.path.abspath(__file__))
    out_raster_path = os.path.join(root_dir, 'naip_out')
    os.makedirs(out_raster_path,exist_ok=True)
    _, query_result, feature_num = query(root_dir, aoi, county=county)
    all_sid_files = download_unzip(query_result, feature_num, root_dir)
    convert_geotiff(all_sid_files, root_dir, county=county)



