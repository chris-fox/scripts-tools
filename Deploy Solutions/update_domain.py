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
    min = arcpy.GetParameterAsText(5)
    max = arcpy.GetParameterAsText(6)
    domain = None

    has_error = False
    if type == 'Coded Value':
        if coded_values.rowCount > 0:
            domain = {'type' : 'codedValue', 'name' : name, 'codedValues' : []}
            for i in range(0, coded_values.rowCount):
                code = coded_values.getValue(i, 0)
                value = coded_values.getValue(i, 1)
            
                if code == '' or value == '':
                   arcpy.AddError("Code and Value cannot be null")
                   has_error = True
                elif field.type == 'SmallInteger' or field.type == 'Integer':
                    try:
                        code = int(code)
                    except ValueError:
                        arcpy.AddError("{0} is an invalid code for an integer field".format(code))
                        has_error = True
                elif field.type == 'Single' or field.type == 'Double':
                    try:
                        code = float(code)
                    except ValueError:
                        arcpy.AddError("{0} is an invalid code for an floating point field".format(code))
                        has_error = True

                domain['codedValues'].append({'code' : code, 'name' : value})
        
        if has_error:
            return
    
    elif type == 'Range':
        range_values = []
        if min == '' or max == '':
            arcpy.AddError("Min and Max cannot be null")
            has_error = True
        elif min == max:
            arcpy.AddError("Min and Max cannot be equal")
            has_error = True
        else:
            for val in [min, max]:
                if field.type == 'SmallInteger' or field.type == 'Integer':
                    try:
                        val = int(val)
                    except ValueError:
                        arcpy.AddError("{0} is an invalid range value for an integer field".format(val))
                        has_error = True
                if field.type == 'Single' or field.type == 'Double':
                    try:
                        val = float(val)
                    except ValueError:
                        arcpy.AddError("{0} is an invalid range value for an floating point field".format(val))
                        has_error = True
                range_values.append(val)

        if has_error:
            return

        if range_values[0] > range_values[1]:
            range_values.insert(0, range_values[1])
            range_values.pop()
        
        domain = {'type': 'range', 'name' : name, 'range' : range_values}
    
    try:
        admin_url = _get_url(arcpy.GetParameterInfo()[0])
        if admin_url == "Invalid URL":
            raise Exception("Input layer or table is not a hosted feature service")
        elif admin_url == "Failed To Connect":
            raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
        update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
        request_parameters['updateDefinition'] = json.dumps(update_defintion)
        arcpy.AddMessage(request_parameters['updateDefinition'])
        resp = _url_request(admin_url + "/updateDefinition", request_parameters, token['referer'], request_type='POST')
    except Exception as e:
        arcpy.AddError("Failed to update domain: {0}".format(str(e)))

def _get_url(parameter):
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
