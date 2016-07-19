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

class ToolValidator(object):
    """Class for validating a tool's parameter values and controlling
    the behavior of the tool's dialog."""

    def __init__(self):
        """Setup arcpy and the list of tool parameters.""" 
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self): 
        """Refine the properties of a tool's parameters. This method is 
        called when the tool is opened."""
        self.params[3].enabled = False
        self.params[4].enabled = False
        self.params[5].enabled = False
        self.params[6].enabled = False

    def updateParameters(self):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""
        if not self.params[0].hasBeenValidated:
            self.params[7].value = _get_fields(self.params[0])
            self.params[1].value = None
            self.params[2].value = None
            self.params[3].enabled = False
            self.params[3].value = None
            self.params[4].enabled = False
            self.params[4].value = None
            self.params[5].enabled = False
            self.params[5].value = None
            self.params[6].enabled = False
            self.params[6].value = None

        if not self.params[1].hasBeenValidated and self.params[0].altered and self.params[7].valueAsText not in ["Failed to connect", "Invalid url"]:
            fields = json.loads(self.params[7].valueAsText)
            field = next((i for i in fields if i['name'] == self.params[1].valueAsText), None)
            if field is not None:
                if field['type'] == 'esriFieldTypeString':
                    self.params[2].filter.list = ['None', 'Coded Value']
                else:
                    self.params[2].filter.list = ['None', 'Coded Value', 'Range']

                if field['domain'] is not None:
                    self.params[3].value = field['domain']['name']
                    self.params[3].enabled = True
                    if 'codedValues' in field['domain']:
                        self.params[2].value = 'Coded Value'
                        coded_values = []
                        for value in field['domain']['codedValues']:
                            coded_values.append([value['code'],value['name']])
                        self.params[4].value = coded_values
                        self.params[4].enabled = True
                        self.params[5].enabled = False
                        self.params[6].enabled = False
                        self.params[5].value = None
                        self.params[6].value = None
                    else:
                        self.params[2].value = 'Range'
                        self.params[5].value = field['domain']['range'][0]
                        self.params[6].value = field['domain']['range'][1]
                        self.params[5].enabled = True
                        self.params[6].enabled = True
                        self.params[4].enabled = False
                        self.params[4].value = []                   
                else:
                    self.params[3].enabled = False
                    self.params[4].enabled = False
                    self.params[5].enabled = False
                    self.params[6].enabled = False
                    self.params[2].value = 'None'
                    self.params[3].value = None
                    self.params[4].value = []
                    self.params[5].value = None
                    self.params[6].value = None
                                
        elif not self.params[2].hasBeenValidated:
            if self.params[2].value == 'None':
                self.params[3].enabled = False
                self.params[4].enabled = False
                self.params[5].enabled = False
                self.params[6].enabled = False
            elif self.params[2].value == 'Coded Value':
                self.params[3].enabled = True 
                self.params[4].enabled = True
                self.params[5].enabled = False
                self.params[6].enabled = False
            elif self.params[2].value == 'Range':
                self.params[3].enabled = True  
                self.params[4].enabled = False
                self.params[5].enabled = True
                self.params[6].enabled = True

    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        if self.params[7].valueAsText == "Invalid URL":
            self.params[0].setErrorMessage("Input layer or table is not a hosted feature service")
        elif self.params[7].valueAsText == "Failed To Connect":
            self.params[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        else:
            self.params[0].clearMessage()
        return

def _get_fields(parameter):
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
        
        admin_url = '{0}/rest/admin/services{1}'.format(url[:index], url[index + len(find_string):])
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'] }
        resp = _url_request(admin_url, request_parameters, token['referer'])
        
        if "serviceItemId" not in resp:
            return "Failed To Connect"

        return json.dumps(resp['fields'])
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
