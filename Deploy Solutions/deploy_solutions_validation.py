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
from arcgis import gis
from urllib.request import urlopen as urlopen
from urllib.request import Request as request
from urllib.parse import urlencode as encode
import configparser as configparser
from io import StringIO

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

class ToolValidator(object):
    """Class for validating a tool's parameter values and controlling
    the behavior of the tool's dialog."""

    def __init__(self):
        """Setup arcpy and the list of tool parameters.""" 
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self): 
        """Refine the properties of a tool's parameters. This method is 
        called when the tool is opened."""
        return

    def updateParameters(self):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""
        if not self.params[0].hasBeenValidated:
            if self.params[4].value is None:
                source = gis.GIS()
                portalId = 'Pu6Fai10JE2L2xUd' #http://statelocaltryit.maps.arcgis.com/
                search_query = 'accountid:{0} AND tags:"{1}"'.format(portalId, 'one.click.solution')               
                items = source.content.search(search_query, max_items=1000)
                solutions = {}
                tag_prefix = 'solution.'
                for item in items:
                    solution_name = next((tag[len(tag_prefix):] for tag in item.tags if tag.startswith('solution.')), None)
                    if solution_name is None:
                        continue
                    if solution_name not in solutions:
                        solutions[solution_name] = []
                    solutions[solution_name].append(item.title)
                self.params[0].filter.list = sorted([solution_name for solution_name in solutions])
                self.params[4].value = json.dumps(solutions)

                portal_description = json.loads(arcpy.GetPortalDescription())
                username = portal_description['user']['username']
                token = arcpy.GetSigninToken()
                request_parameters = {'f' : 'json', 'token' : token['token'] }
                url = "{0}/sharing/rest/content/users/{1}".format(arcpy.GetActivePortalURL(), username)
                resp = _url_request(url, request_parameters, token['referer'])
                self.params[3].filter.list = [folder['title'] for folder in resp['folders']]
                return

            solutions = json.loads(self.params[4].valueAsText)        
            solution_name = self.params[0].valueAsText
            self.params[1].filter.list = sorted([map_app for map_app in solutions[solution_name]])
            self.params[1].value = arcpy.ValueTable() # reset parameter value
    
    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        self.params[3].clearMessage()
