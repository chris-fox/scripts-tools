"""
-------------------------------------------------------------------------------
 | Copyright 2016 Esri
 |
 | Licensed under the Apache License, Version 2.0 (the "License");
 | you may not use this file except in compliance with the License.
 | You may obtain a copy of the License at
 |
 |    http://www.apache.org/licenses/LICENSE-2.0
 |
 | Unless required by applicable law or agreed to in writing, software
 | distributed under the License is distributed on an "AS IS" BASIS,
 | WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 | See the License for the specific language governing permissions and
 | limitations under the License.
 ------------------------------------------------------------------------------
 """

import gzip, json, io, arcpy
from urllib.request import urlopen as urlopen
from urllib.request import Request as request
from urllib.parse import urlencode as encode
from urllib.parse import urlparse as parse

PORTAL_ID = 'Pu6Fai10JE2L2xUd' #http://statelocaltryit.maps.arcgis.com/
VALIDATION_JSON = {}

def get_validation_json():
    return VALIDATION_JSON

def set_validation_json(validation_json):
    global VALIDATION_JSON
    VALIDATION_JSON = validation_json

def url_request(url, request_parameters, referer, request_type='GET', repeat=0, raise_on_failure=True):
    """Send a new request and format the json response.
    Keyword arguments:
    url - the url of the request
    request_parameters - a dictionay containing the name of the parameter and its correspoinsding value
    request_type - the type of request: 'GET', 'POST'
    repeat - the nuber of times to repeat the request in the case of a failure
    error_text - the message to log if an error is returned
    raise_on_failure - indicates if an exception should be raised if an error is returned and repeat is 0"""
    if request_type == 'GET':
        req = request('?'.join((url, encode(request_parameters))))
    else:
        headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',}
        req = request(url, encode(request_parameters).encode('UTF-8'), headers)

    req.add_header('Accept-encoding', 'gzip')
    if referer is not None:
        req.add_header('Referer', referer)

    response = urlopen(req)

    if response.info().get('Content-Encoding') == 'gzip':
        buf = io.BytesIO(response.read())
        with gzip.GzipFile(fileobj=buf) as gzip_file:
            response_bytes = gzip_file.read()
    else:
        response_bytes = response.read()

    response_text = response_bytes.decode('UTF-8')
    response_json = json.loads(response_text)

    if "error" in response_json:
        if repeat == 0:
            if raise_on_failure:
                raise Exception(response_json)
            return response_json

        repeat -= 1
        time.sleep(2)
        response_json = self._url_request(
            url, request_parameters, referer, request_type, repeat, raise_on_failure)

    return response_json

def get_fields(parameter):
    admin_url = get_admin_url(parameter)
    if admin_url in ["Invalid URL", "Failed To Connect"]:
        return admin_url

    try:      
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'] }
        resp = url_request(admin_url, request_parameters, token['referer'])
        
        if "serviceItemId" not in resp:
            return "Failed To Connect"

        return json.dumps(resp['fields'])
    except:
        return "Failed To Connect"

def get_admin_url(parameter):
    url = None
    input = parameter.value
    if type(input) == arcpy._mp.Layer: # Layer in the map
        connection_props = input.connectionProperties
        if connection_props['workspace_factory'] == 'FeatureService':
            url = '{0}/{1}'.format(connection_props['connection_info']['url'], connection_props['dataset'])
    else:
        input = parameter.valueAsText 
        pieces = parse(input)
        if pieces.scheme in ['http', 'https']: # URL
            url = input
        else: # Table in the map
            prj = arcpy.mp.ArcGISProject('Current')
            for map in prj.listMaps():
                for table in map.listTables():
                    if table.name == input:
                        connection_props = table.connectionProperties
                        if connection_props['workspace_factory'] == 'FeatureService':
                            url = '{0}/{1}'.format(connection_props['connection_info']['url'], connection_props['dataset'])
    if url is None:
        return "Invalid URL"

    try:      
        find_string = "/rest/services"
        index = url.find(find_string)
        if index == -1:
            return "Invalid URL"
        
        return '{0}/rest/admin/services{1}'.format(url[:index], url[index + len(find_string):])
    except:
        return "Failed To Connect"