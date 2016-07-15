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
import os, traceback, gzip, json, io, arcpy
from urllib.request import urlopen as urlopen
from urllib.request import Request as request
from urllib.parse import urlencode as encode
from urllib.parse import urlparse as parse
import configparser as configparser
from io import StringIO

def main():
    field = arcpy.ListFields(arcpy.GetParameterAsText(0), arcpy.GetParameterAsText(1))[0]
    type = arcpy.GetParameterAsText(2)
    name = arcpy.GetParameterAsText(3)
    coded_values = arcpy.GetParameter(4)
    min = arcpy.GetParameter(5)
    max = arcpy.GetParameter(6)
    domain = None

    if type == 'Coded Value':
        domain = {'type' : 'codedValue', 'name' : name, 'codedValues' : []}
        for i in range(0, coded_values.rowCount):
            code = coded_values.getValue(i, 0)
            error_found = False
            if field.type == 'SmallInteger' or field.type == 'Integer':
                try:
                    code = int(code)
                except ValueError:
                    arcpy.AddError("{0} is invalid code for an integer field".format(code))
                    error_found = True
            elif field.type == 'Single' or field.type == 'Double':
                try:
                    code = float(code)
                except ValueError:
                    arcpy.AddError("{0} is invalid code for an floating point field".format(code))
                    error_found = True
            domain['codedValues'].append({'code' : code, 'name' : coded_values.getValue(i, 1)})
        if error_found:
            return
    elif type == 'Range':
        domain = {'type': 'range', 'name' : name, 'range' : [min, max]}

    try:
        admin_url = _get_admin_url(arcpy.GetParameterInfo()[0])
        if admin_url is None:
            raise Exception("Input layer or table is not a feature service")
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
        update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
        request_parameters['updateDefinition'] = json.dumps(update_defintion)
        _url_request(admin_url, request_parameters, token['referer'], request_type='POST')
    except Exception as e:
        arcpy.AddError("Failed to update domain: {0}".format(e.args[0]))

def _get_admin_url(parameter):
    url = _get_url(parameter)
    if url is None:
        return None
    find_string = "/rest/services"
    index = url.find(find_string)
    if index == -1:
        return None
    return '{0}/rest/admin/services{1}/updateDefinition'.format(url[:index], url[index + len(find_string):])

def _get_url(parameter):
    input = parameter.value
    if type(input) == arcpy._mp.Layer: # Layer in the map
        connection_props = input.connectionProperties
        if connection_props['workspace_factory'] != 'FeatureService':
            return None
        return '{0}/{1}'.format(connection_props['connection_info']['url'], connection_props['dataset'])
    else:
        input = parameter.valueAsText 
        pieces = parse(input)
        if pieces.scheme in ['http', 'https']: # URL
            return input
        else: # Table in the map
            prj = arcpy.mp.ArcGISProject('Current')
            for map in prj.listMaps():
                for table in map.listTables():
                    if table.name == input:
                        connection_props = table.connectionProperties
                        if connection_props['workspace_factory'] == 'FeatureService':
                            return '{0}/{1}'.format(connection_props['connection_info']['url'], connection_props['dataset'])
            return None

def _url_request(url, request_parameters, referer, request_type='GET', repeat=0, raise_on_failure=True):
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

if __name__ == "__main__":
    main()
