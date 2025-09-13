# -*- coding: utf-8 -*-
"""
Created on Sat Aug 30 19:08:00 2025

@author: Feng
"""
from bs4 import BeautifulSoup
import requests
import json, re
import os
import pandas as pd
import sys, path
directory = path.path(__file__).abspath()
sys.path.append(directory.parent.parent)
from parentdirectory.manual_grab import download_file_from_box

def download_file(url):
    local_filename = url.split('/')[-1]
    # NOTE the stream=True parameter below
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                f.write(chunk)
    return local_filename


def build_ortholist(base_url_input,page_index, box_id_num):
    url = f"{base_url_input}/folder/{box_id_num}?page={page_index}"
    file_root = f"{base_url_input}/file/" #https://nrcs.app.box.com/v/naip/file/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # grab the first <script> content
    script_text = soup.find_all("script")
    
    
    for script_item in script_text:
        text_item = script_item.string
        if text_item is not None:
            # regex to extract the JSON part inside "Box.postStreamData = {...};"
            match = re.search(r'Box\.postStreamData\s*=\s*({.*});', text_item, re.DOTALL)    
            if match:
                json_text = match.group(1)
                # load as JSON
                data = json.loads(json_text)
                
                # now you can access the "item" parts
                #shared_item = data.get("/app-api/enduserapp/shared-item", {})
                shared_folder = data.get("/app-api/enduserapp/shared-folder")
                items =  shared_folder.get("items")
    ids = []
    zip_files = []
    url_files = []            
    for ortho_item in items:
        ortho_id = ortho_item.get("id")
        ids.append(ortho_id)
        zip_files.append(ortho_item.get("name"))
        url_files.append(f"{file_root}{ortho_id}")
    return ids, zip_files, url_files

def build_helper(base_url,box_id):
    ids_all = []
    zip_files_all = []
    url_files_all = []
    for page_inx in range(1, 10, 1):
        ids_single, zip_files_singe, url_files_single = build_ortholist(base_url, page_inx, box_id)
        if len(ids_single)>0:
            ids_all.extend(ids_single)
            zip_files_all.extend(zip_files_singe)
            url_files_all.extend(url_files_single)
    return ids_all, zip_files_all, url_files_all
    
if __name__ == "__main__":
    out_table = "/mnt/naip_out"
    os.makedirs(out_table, exist_ok=True)
    base_link = "https://nrcs.app.box.com/v/naip"
    box_id_c = "180264749881"
    box_id_n = "180267566618"
    ext_ids_c, ext_zip_c, ext_url_c = build_helper(base_link, box_id_c)
    ext_ids_n, ext_zip_n, ext_url_n = build_helper(base_link, box_id_n)
    table_data_c = {"ID_c": ext_ids_c, "URL_c": ext_url_c, "ORTHO_c": ext_zip_c}
    table_data_n = {"ID_n": ext_ids_n, "URL_n": ext_url_n, "ORTHO_n": ext_zip_n}
    ext_ortho_table_c = pd.DataFrame(table_data_c)
    ext_ortho_table_n = pd.DataFrame(table_data_n)
    ext_ortho_table = ext_ortho_table_c.merge(ext_ortho_table_n, how='inner', left_index=True, right_index=True)
    ext_ortho_table.to_csv(os.path.join(out_table,"compiled_ortho_link.csv"))

    # for inx, url in enumerate(ext_url):
    #     try:
    #         download_file_from_box(url, os.path.join("D:", 'naip', ext_zip[inx]))
    #     except Exception as e:
    #         print(f"Download failed for {url}: {e}")

