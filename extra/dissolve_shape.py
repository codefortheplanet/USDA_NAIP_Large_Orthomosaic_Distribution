# -*- coding: utf-8 -*-
"""
Created on Sun Aug 31 12:06:57 2025

@author: Feng
"""

### upzip ortho zips from naip data Box storage and extract the shapefiles into a directory

import os
from zipfile import ZipFile
from glob import glob
import re
from osgeo import ogr, osr

zip_path = r'/mnt'
out_shp_dir = os.path.join(zip_path, 'ortho_shps')
os.makedirs(out_shp_dir,exist_ok=True)
out_merge_dir = os.path.join(zip_path, 'merge_shps')
os.makedirs(out_merge_dir,exist_ok=True)

patterns = r"^.au|^.si|^.tx|_s_"
pattern_shp = r".shp"

zip_list = glob(os.path.join(zip_path,'*.zip'))
shp_list = []
spatial_ref = []

driver = ogr.GetDriverByName('ESRI Shapefile')
for zip_ortho in zip_list:
    with ZipFile(zip_ortho, 'r') as zipObj:
        # Get a list of all archived file names from the zip
        listOfFileNames = zipObj.namelist()
        #print (listOfFileNames)
        # Iterate over the file names
        for fileName in listOfFileNames:
            #check the excluding file condition.
            match = re.search(patterns,fileName)
            if match is None:
                #print (fileName)
                zipObj.extract(fileName, out_shp_dir)
                match1 = re.search(pattern_shp, fileName)
                if match1 is not None:
                    out_shp_path = os.path.join(out_shp_dir,fileName)
                    shp_list.append(out_shp_path)

for shp in shp_list:
    with driver.Open(shp, 0) as source_ds:
        layer = source_ds.GetLayer()
        ref = layer.GetSpatialRef()
        spatial_ref.append(ref.GetAuthorityCode(None))
                            
spatial_ref = list(set(spatial_ref))
spatial_ref.append('4269') #NAD83

target_srs = osr.SpatialReference()
target_srs.ImportFromEPSG(4269)  # Web Mercator
target_srs.SetWellKnownGeogCS( "CRS83" )


# Step 3: Create new shapefile
dissolved_shapefile_path = os.path.join(out_merge_dir,'merged_dissolved_geopackage.gpkg')
driver1 = ogr.GetDriverByName('GPKG')
#dissolved_shapefile_path = r'C:/Users/Feng/Documents/dissolved_shapefile.shp'
if os.path.exists(dissolved_shapefile_path):
    driver1.DeleteDataSource(dissolved_shapefile_path)

dissolved_ds = driver1.CreateDataSource(dissolved_shapefile_path)
srs = osr.SpatialReference()
#data_source = driver.Open(shp_list[0], 0)
dissolved_layers = []
for ref in spatial_ref:
    srs.ImportFromEPSG(int(ref))
    dissolved_layer = dissolved_ds.CreateLayer('dissolved_layer_EPSG'+ref, srs, geom_type=ogr.wkbPolygon)    
    # Add a new field (column)
    field_defn = ogr.FieldDefn("OrthoName_c", ogr.OFTString)  # name + type
    dissolved_layer.CreateField(field_defn)
    field_defn = ogr.FieldDefn("OrthoName_n", ogr.OFTString)  # name + type
    dissolved_layer.CreateField(field_defn)
    field_defn = ogr.FieldDefn("OID", ogr.OFTInteger)  # name + type
    dissolved_layer.CreateField(field_defn)
    dissolved_layers.append(dissolved_layer)

driver = ogr.GetDriverByName('ESRI Shapefile')
for inx, shapefile_path in enumerate(shp_list):
    # # Step 1: Open the shapefile
    single_shape = os.path.join(os.path.dirname(shapefile_path), os.path.basename(shapefile_path).split('.')[0] + '_explode.shp')
    os.system(f'ogr2ogr -f "ESRI Shapefile" -explodecollections {single_shape} {shapefile_path}') 
    data_source = driver.Open(single_shape, 0)
    
    # Step 2: Run dissolve SQL on input data
    layer = data_source.GetLayer()
    ref = layer.GetSpatialRef()
    epsg_code = ref.GetAuthorityCode(None)
    sql_query = f'SELECT ST_Union(geometry) AS geom FROM "{layer.GetName()}"'
    result_layer = data_source.ExecuteSQL(sql_query, dialect="SQLITE")
    source_srs = osr.SpatialReference()
    source_srs.ImportFromEPSG(int(epsg_code))
    coord_transform = osr.CoordinateTransformation(source_srs, target_srs)

    # Step 4: Copy dissolved geometry
    for feat in result_layer:
        out_feat = ogr.Feature(dissolved_layers[spatial_ref.index(epsg_code)].GetLayerDefn())
        geom = feat.GetGeometryRef().Clone()
        out_feat.SetGeometry(geom)
        # Set value for new column
        out_feat.SetField("OrthoName_c", os.path.basename(zip_list[inx]))  # for example, fixed value = 1
        out_feat.SetField("OrthoName_n", os.path.basename(zip_list[inx]).split('_hc_')[0] + '_hn_' + os.path.basename(zip_list[inx]).split('_hc_')[1])  # for example, fixed value = 1
        out_feat.SetField("OID", inx)
        dissolved_layers[spatial_ref.index(epsg_code)].CreateFeature(out_feat)
        out_feat = None
        
        out_feat = ogr.Feature(dissolved_layers[spatial_ref.index('4269')].GetLayerDefn())
        geom.Transform(coord_transform)
        out_feat.SetGeometry(geom)
        # Set value for new column
        out_feat.SetField("OrthoName_c", os.path.basename(zip_list[inx]))  # for example, fixed value = 1
        out_feat.SetField("OrthoName_n", os.path.basename(zip_list[inx]).split('_hc_')[0] + '_hn_' + os.path.basename(zip_list[inx]).split('_hc_')[1])  # for example, fixed value = 1
        out_feat.SetField("OID", inx)
        dissolved_layers[spatial_ref.index('4269')].CreateFeature(out_feat)
        out_feat = None
        # Step 5: Cleanup
    data_source.ReleaseResultSet(result_layer)    
    data_source = None
dissolved_ds = None
