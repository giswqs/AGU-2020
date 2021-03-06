#----------------------------------------------------------------------
# Functions for 2020 AGU Workshop tutorial notebooks
#
#----------------------------------------------------------------------

from netrc import netrc
from platform import system
from getpass import getpass
from urllib import request
from http.cookiejar import CookieJar
from os.path import join, expanduser
import requests
from pprint import pprint
import json
import os
import requests
from xml.etree import ElementTree as ET
import shutil
import time
import zipfile
import io
import h5py
from pathlib import Path
import pandas as pd
import numpy as np


TOKEN_DATA = ("<token>"
              "<username>%s</username>"
              "<password>%s</password>"
              "<client_id>PODAAC CMR Client</client_id>"
              "<user_ip_address>%s</user_ip_address>"
              "</token>")


def setup_cmr_token_auth(endpoint: str='cmr.earthdata.nasa.gov'):
    ip = requests.get("https://ipinfo.io/ip").text.strip()
    return requests.post(
        url="https://%s/legacy-services/rest/tokens" % endpoint,
        data=TOKEN_DATA % (input("Username: "), getpass("Password: "), ip),
        headers={'Content-Type': 'application/xml', 'Accept': 'application/json'}
    ).json()['token']['id']


def setup_earthdata_login_auth(endpoint: str='urs.earthdata.nasa.gov'):
    netrc_name = "_netrc" if system()=="Windows" else ".netrc"
    try:
        username, _, password = netrc(file=join(expanduser('~'), netrc_name)).authenticators(endpoint)
    except (FileNotFoundError, TypeError):
        print('Please provide your Earthdata Login credentials for access.')
        print('Your info will only be passed to %s and will not be exposed in Jupyter.' % (endpoint))
        username = input('Username: ')
        password = getpass('Password: ')
    manager = request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, endpoint, username, password)
    auth = request.HTTPBasicAuthHandler(manager)
    jar = CookieJar()
    processor = request.HTTPCookieProcessor(jar)
    opener = request.build_opener(auth, processor)
    request.install_opener(opener)


def search_granules(search_parameters, token, geojson=None, output_format="json"):
    """
    Performs a granule search with token authentication for restricted results
    
    :search_parameters: dictionary of CMR search parameters
    :token: CMR token needed for restricted search
    :geojson: filepath to GeoJSON file for spatial search
    :output_format: select format for results https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html#supported-result-formats
    
    :returns: if hits is greater than 0, search results are returned in chosen output_format, otherwise returns None.
    """
    search_url = "https://cmr.earthdata.nasa.gov/search/granules"
    
    # add token to search parameters
    search_parameters['token'] = token
    
    if geojson:
        files = {"shapefile": (geojson, open(geojson, "r"), "application/geo+json")}
    else:
        files = None
    
    
    parameters = {
        "scroll": "true",
        "page_size": 100,
    }
    
    try:
        response = requests.post(f"{search_url}.{output_format}", params=parameters, data=search_parameters, files=files)
        response.raise_for_status()
    except HTTPError as http_err:
        print(f"HTTP Error: {http_error}")
    except Exception as err:
        print(f"Error: {err}")
    
    hits = int(response.headers['CMR-Hits'])
    if hits > 0:
        print(f"Found {hits} files")
        results = json.loads(response.content)
        granules = []
        granules.extend(results['feed']['entry'])
        granule_sizes = [float(granule['granule_size']) for granule in granules]
        print(f"The total size of all files is {sum(granule_sizes):.2f} MB")
        return response.json()
    else:
        print("Found no hits")
        return

def search_services(search_parameters, token, output_format="json"):
    """
    Performs a granule search with token authentication for restricted results
    
    :search_parameters: dictionary of CMR search parameters
    :token: CMR token needed for restricted search
    :output_format: select format for results https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html#supported-result-formats
    
    :returns: if hits is greater than 0, search results are returned in chosen output_format, otherwise returns None.
    """
    collection_url = "https://cmr.earthdata.nasa.gov/search/collections"
    
    # add token to search parameters
    search_parameters['token'] = token
    
    parameters = {
        "scroll": "true",
        "page_size": 100,
    }
    
    try:
        response = requests.post(f"{collection_url}.{output_format}", params=parameters, data=search_parameters)
        response.raise_for_status()
    except HTTPError as http_err:
        print(f"HTTP Error: {http_error}")
    except Exception as err:
        print(f"Error: {err}")
    
    hits = int(response.headers['CMR-Hits'])
    if hits > 0:
        response = response.json()
        if 'services' in response['feed']['entry'][0]['associations']: 
            services = response['feed']['entry'][0]['associations']['services']
            output_format = "umm_json"
            service_url = "https://cmr.earthdata.nasa.gov/search/services"
            for i in range(len(services)):
                response = requests.get(f"{service_url}.{output_format}?concept-id={services[i]}")
                response = response.json()
                if 'ServiceOptions' in response['items'][0]['umm']: pprint(response['items'][0]['umm']['ServiceOptions'])
        else:
            print("Found no services")
        return
    else:
        print("Found no hits")
        return
    

def request_nsidc_data(API_request):
    """
    Performs a data customization and access request from NSIDC's API/
    Creates an output folder in the working directory if one does not already exist.
    
    :API_request: NSIDC API endpoint; see https://nsidc.org/support/how/how-do-i-programmatically-request-data-services for more info
    on how to configure the API request.
    
    """

    path = str(os.getcwd() + '/Outputs') # Create an output folder if the folder does not already exist.
    if not os.path.exists(path):
        os.mkdir(path)
        
    base_url = 'https://n5eil02u.ecs.nsidc.org/egi/request'

    
    r = request.urlopen(API_request)
    esir_root = ET.fromstring(r.read())
    orderlist = []   # Look up order ID
    for order in esir_root.findall("./order/"):
        orderlist.append(order.text)
    orderID = orderlist[0]
    statusURL = base_url + '/' + orderID # Create status URL
    print('Order status URL: ', statusURL)
    request_response = request.urlopen(statusURL) # Find order status  
    request_root = ET.fromstring(request_response.read())
    statuslist = []
    for status in request_root.findall("./requestStatus/"):
        statuslist.append(status.text)
    status = statuslist[0]
    while status == 'pending' or status == 'processing': #Continue loop while request is still processing
        print('Job status is ', status,'. Trying again.')
        time.sleep(10)
        loop_response = request.urlopen(statusURL)
        loop_root = ET.fromstring(loop_response.read())
        statuslist = [] #find status
        for status in loop_root.findall("./requestStatus/"):
            statuslist.append(status.text)
        status = statuslist[0]
        if status == 'pending' or status == 'processing':
            continue
    if status == 'complete_with_errors' or status == 'failed': # Provide complete_with_errors error message:
        messagelist = []
        for message in loop_root.findall("./processInfo/"):
            messagelist.append(message.text)
        print('Job status is ', status)
        print('error messages:')
        pprint(messagelist)
    if status == 'complete' or status == 'complete_with_errors':# Download zipped order if status is complete or complete_with_errors
        downloadURL = 'https://n5eil02u.ecs.nsidc.org/esir/' + orderID + '.zip'
        print('Job status is ', status)
        print('Zip download URL: ', downloadURL)
        print('Beginning download of zipped output...')
        zip_response = request.urlopen(downloadURL)
        with zipfile.ZipFile(io.BytesIO(zip_response.read())) as z:
            z.extractall(path)
        print('Download is complete.')
    else: print('Request failed.')
    
    # Clean up Outputs folder by removing individual granule folders 
    for root, dirs, files in os.walk(path, topdown=False):
        for file in files:
            try:
                shutil.move(os.path.join(root, file), path)
            except OSError:
                pass
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    return  

#     loop_response = request.urlopen(smap_job_url)
#     loop_results = loop_response.read()

def request_harmony_data(search_parameters, token):
    """
    Performs a data customization and access request from Harmony.
    
    :search_parameters: dictionary of CMR search parameters
    :token: CMR token needed for restricted search
    
    """
    # find cmr collection id
    cmr_collections_url = 'https://cmr.earthdata.nasa.gov/search/collections.json'
    cmr_response = requests.get(cmr_collections_url, params=search_parameters)
    cmr_results = json.loads(cmr_response.content) # Get json response from CMR collection metadata

    collectionlist = [el['id'] for el in cmr_results['feed']['entry']]
    search_parameters['collection_id'] = collectionlist[0]
    
    harmony_root = 'https://harmony.earthdata.nasa.gov'

    lat_list = ((search_parameters['bounding_box'].split(","))[1],":",(search_parameters['bounding_box'].split(","))[3])
    search_parameters['lat'] = "(" + ''.join(lat_list) + ")"
    lon_list = ((search_parameters['bounding_box'].split(","))[0],":",(search_parameters['bounding_box'].split(","))[2])
    search_parameters['lon'] = "(" + ''.join(lon_list) + ")"
    t1 = search_parameters['temporal'].split(',')[0]
    t2 = search_parameters['temporal'].split(',')[1]
    search_parameters['time'] = f'("{t1}":"{t2}")'

    harmony_url = harmony_root+'/{collection_id}/ogc-api-coverages/1.0.0/collections/all/coverage/rangeset?&subset=lat{lat}&subset=lon{lon}&subset=time{time}'.format(**search_parameters)
    print('Request URL', harmony_url)
    r = request.urlopen(harmony_url)
    harmony_response = r.read()
    async_json = json.loads(harmony_response)
    pprint(async_json)

    jobConfig = {
        'jobID': async_json['jobID']
    }

    job_url = harmony_root+'/jobs/{jobID}'.format(**jobConfig)
    print('Job URL', job_url)

    job_response = request.urlopen(job_url)
    job_results = job_response.read()
    job_json = json.loads(job_results)

    print('Job response:')
    print()
    pprint(job_json)

    #Continue loop while request is still processing
    while job_json['status'] == 'running' and job_json['progress'] < 100: 
        print('Job status is running. Progress is ', job_json['progress'], '%. Trying again.')
        time.sleep(10)
        loop_response = request.urlopen(job_url)
        loop_results = loop_response.read()
        job_json = json.loads(loop_results)
        if job_json['status'] == 'running':
            continue

    if job_json['progress'] == 100:
        print('Job progress is 100%. Output links printed below:')
        links = [link for link in job_json['links'] if link.get('rel', 'data') == 'data'] #list of data links from response
        for i in range(len(links)):
            link_dict = links[i] 
            print(link_dict['href'])
            filepath = link_dict['href'].split('/')[-1]
            file_ = open(filepath, 'wb')
            response = request.urlopen(link_dict['href'])
            file_.write(response.read())
            file_.close()
    return

def load_icesat2_as_dataframe(filepath, VARIABLES):
    '''
    Load points from an ICESat-2 granule 'gt<beam>' groups as DataFrame of points. Uses VARIABLES mapping
    to select subset of '/gt<beam>/...' variables  (Assumes these variables share dimensions)
    Arguments:
        filepath to ATL0# granule
    '''
    
    ds = h5py.File(filepath, 'r')

    # Get dataproduct name
    dataproduct = ds.attrs['identifier_product_type'].decode()
    # Convert variable paths to 'Path' objects for easy manipulation
    variables = [Path(v) for v in VARIABLES[dataproduct]]
    # Get set of beams to extract individially as dataframes combining in the end
    beams = {list(v.parents)[-2].name for v in variables}
    
    dfs = []
    for beam in beams:
        data_dict = {}
        beam_variables = [v for v in variables if beam in str(v)]
        for variable in beam_variables:
            # Use variable 'name' as column name. Beam will be specified in 'beam' column
            column = variable.name
            variable = str(variable)
            try:
                values = ds[variable][:]
                # Convert invalid data to np.nan (only for float columns)
                if 'float' in str(values.dtype):
                    if 'valid_min' in ds[variable].attrs:
                        values[values < ds[variable].attrs['valid_min']] = np.nan
                    if 'valid_max' in ds[variable].attrs:
                        values[values > ds[variable].attrs['valid_max']] = np.nan
                    if '_FillValue' in ds[variable].attrs:
                        values[values == ds[variable].attrs['_FillValue']] = np.nan
                    
                data_dict[column] = values
            except KeyError:
                print(f'Variable {variable} not found in {filepath}. Likely an empty granule.')
                raise
                
        df = pd.DataFrame.from_dict(data_dict)
        df['beam'] = beam
        dfs.append(df)
        
    df = pd.concat(dfs, sort=True)
    # Add filename column for book-keeping and reset index
    df['filename'] = Path(filepath).name
    df = df.reset_index(drop=True)
    
    return df

