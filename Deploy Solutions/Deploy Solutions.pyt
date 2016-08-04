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
import arcpy, json, uuid, re, tempfile, os, copy, io, gzip, webbrowser
from arcgis import gis, lyr
from urllib.request import urlopen as urlopen
from urllib.request import Request as request
from urllib.parse import urlencode as encode
from urllib.parse import urlparse as parse

PORTAL_ID = 'Pu6Fai10JE2L2xUd' #http://statelocaltryit.maps.arcgis.com/
TAG = 'one.click.solution'
TEXT_BASED_ITEM_TYPES = ['Web Map', 'Feature Service', 'Map Service', 'Operation View',
                                   'Image Service', 'Feature Collection', 'Feature Collection Template',
                                   'Web Mapping Application', 'Mobile Application', 'Symbol Set', 'Color Set']

#region Toolbox and Tools

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Deploy Solutions"
        self.alias = "solutions"

        # List of tool classes associated with this toolbox
        self.tools = [DeploySolutionsTool, DeploySolutionsLocalTool, DownloadSolutionsTool, 
                      UpdateDomainTool, AlterFieldAliasTool, OpenWebMap]

class DeploySolutionsTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Deploy Solutions"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Solution Group",
            name="solution_group",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Solutions",
            name="solutions",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param2 = arcpy.Parameter(
            displayName="Extent",
            name="extent",
            datatype="GPExtent",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Copy Sample Data",
            name="copy_sample_data",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param3.value = False

        param4 = arcpy.Parameter(
            displayName="Folder",
            name="folder",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3, param4, param5]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            if not parameters[5].value:
                source = gis.GIS()
                search_query = 'accountid:{0} AND tags:"{1}"'.format(PORTAL_ID, TAG)               
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
                parameters[0].filter.list = sorted([solution_name for solution_name in solutions])

                target = gis.GIS('pro')
                folders = target.users.me.folders
                parameters[4].filter.list = sorted([folder['title'] for folder in folders])
                validation_json =  { 'solutions' : solutions, 'folders' : folders }
                parameters[5].value = json.dumps(validation_json)

            if parameters[0].value:
                validation_json = json.loads(parameters[5].valueAsText)  
                solutions = validation_json['solutions']   
                solution_name = parameters[0].valueAsText
                parameters[1].filter.list = sorted([map_app for map_app in solutions[solution_name]])
                parameters[1].value = arcpy.ValueTable()

        if not parameters[4].hasBeenValidated:
            validation_json = json.loads(parameters[5].valueAsText)  
            folders = validation_json['folders']
            if parameters[4].value:
                parameters[4].filter.list = sorted(set([parameters[4].valueAsText] + [folder['title'] for folder in folders]))
            else:
                parameters[4].filter.list = sorted([folder['title'] for folder in folders])

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        connection = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
            token = arcpy.GetSigninToken()
            connection = {'target' : target, 'url' : arcpy.GetActivePortalURL(), 
                          'username' : target.users.me.username, 
                          'token' : token['token'], 'referer' : token['referer'], 'local' : False }
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

        if connection:             
            # Get the input parameters for creating from local items on disk
            solution_group = parameters[0].valueAsText
            value_table = parameters[1].value
            solutions = [value_table.getValue(i, 0) for i in range(0, value_table.rowCount)]
            solutions = sorted(list(set(solutions)))
            extent = _get_default_extent(parameters[2].value)
            copy_features = parameters[3].value
            output_folder = parameters[4].valueAsText
            parameters[5].value = ''

            # Clone the solutions
            _create_solutions(connection, solution_group, solutions, extent, copy_features, output_folder)
            return

class DeploySolutionsLocalTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Deploy Solutions (Local)"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Items Folder",
            name="items_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Solution Group",
            name="solution_group",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Solutions",
            name="solutions",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param3 = arcpy.Parameter(
            displayName="Extent",
            name="extent",
            datatype="GPExtent",
            parameterType="Optional",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Copy Sample Data",
            name="copy_sample_data",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param4.value = False

        param5 = arcpy.Parameter(
            displayName="Folder",
            name="folder",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3, param4, param5, param6]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            if parameters[0].value:
                solutions_definition_file = os.path.join(parameters[0].valueAsText, 'SolutionDefinitions.json') 
                if os.path.exists(solutions_definition_file):
                    with open(solutions_definition_file, 'r') as file:
                        content = file.read() 
                        definitions = json.loads(content)
                        parameters[1].filter.list = sorted([solution_group for solution_group in definitions['Solution Groups']])

            if not parameters[5].value:
                target = gis.GIS('pro')
                folders = target.users.me.folders
                parameters[5].filter.list = sorted([folder['title'] for folder in folders])
                validation_json = { 'folders' : folders }
                parameters[6].value = json.dumps(validation_json)
        
        if not parameters[1].hasBeenValidated and parameters[1].value:
            solutions_definition_file = os.path.join(parameters[0].valueAsText, 'SolutionDefinitions.json') 
            if os.path.exists(solutions_definition_file):
                solution_group = parameters[1].valueAsText
                with open(solutions_definition_file, 'r') as file:
                    content = file.read() 
                    definitions = json.loads(content)
                    if solution_group in definitions['Solution Groups']:
                        parameters[2].filter.list = sorted(definitions['Solution Groups'][solution_group])

        if not parameters[5].hasBeenValidated:
            validation_json = json.loads(parameters[6].valueAsText)  
            folders = validation_json['folders']
            if parameters[5].value:
                parameters[5].filter.list = sorted(set([parameters[5].valueAsText] + [folder['title'] for folder in folders]))
            else:
                parameters[5].filter.list = sorted([folder['title'] for folder in folders])

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""        
        return

    def execute(self, parameters, messages):
        connection = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
            token = arcpy.GetSigninToken()
            connection = {'target' : target, 'url' : arcpy.GetActivePortalURL(), 
                          'username' : target.users.me.username, 
                          'token' : token['token'], 'referer' : token['referer'], 'local' : True }
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

        if connection:
            connection['source directory'] = parameters[0].valueAsText
            solution_group = parameters[1].valueAsText
            value_table = parameters[2].value
            solutions = [value_table.getValue(i, 0) for i in range(0, value_table.rowCount)]
            solutions = sorted(list(set(solutions)))
            extent = _get_default_extent(parameters[3].value)
            copy_features = parameters[4].value
            output_folder = parameters[5].valueAsText
            parameters[6].value = ''
                            
            # Clone the solutions
            _create_solutions(connection, solution_group, solutions, extent, copy_features, output_folder)
            return

class DownloadSolutionsTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Download Solutions"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Solution Group",
            name="solution_group",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Solutions",
            name="solutions",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param2 = arcpy.Parameter(
            displayName="Copy Sample Data",
            name="copy_sample_data",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param2.value = False

        param3 = arcpy.Parameter(
            displayName="Output Directory",
            name="output_directory",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3, param4]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            if parameters[4].value is None:
                source = gis.GIS()
                search_query = 'accountid:{0} AND tags:"{1}"'.format(PORTAL_ID, TAG)               
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
                parameters[0].filter.list = sorted([solution_name for solution_name in solutions])
                parameters[4].value = json.dumps(solutions)

            if parameters[0].value:
                solutions = json.loads(parameters[4].valueAsText)     
                solution_name = parameters[0].valueAsText
                parameters[1].filter.list = sorted([map_app for map_app in solutions[solution_name]])
                parameters[1].value = arcpy.ValueTable()

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        connection = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
            token = arcpy.GetSigninToken()
            connection = {'target' : target, 'url' : arcpy.GetActivePortalURL(), 
                          'username' : target.users.me.username, 
                          'token' : token['token'], 'referer' : token['referer'], 'local' : False }
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

        if connection:             
            # Download the items
            solution_group = parameters[0].valueAsText
            value_table = parameters[1].value
            solutions = [value_table.getValue(i, 0) for i in range(0, value_table.rowCount)]
            solutions = sorted(list(set(solutions)))
            copy_features = parameters[2].value
            output_directory = parameters[3].valueAsText
            parameters[4].value = ''
            _download_solutions(connection, solution_group, solutions, copy_features, output_directory)
            return

class UpdateDomainTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Update Domains"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Layer or Table",
            name="input_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Field",
            name="field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ['Short', 'Long', 'Float', 'Double', 'Text']
        param1.parameterDependencies = [param0.name]

        param2 = arcpy.Parameter(
            displayName="Type",
            name="type",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param2.filter.list = ['None', 'Coded Value', 'Range']

        param3 = arcpy.Parameter(
            displayName="Name",
            name="name",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            enabled=False)

        param4 = arcpy.Parameter(
            displayName="Domain",
            name="domain",
            datatype="GPValueTable",
            parameterType="Optional",
            direction="Input",
            enabled=False)
        param4.columns = [['GPString', 'Code'], ['GPString', 'Value']]

        param5 = arcpy.Parameter(
            displayName="Min",
            name="min",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input",
            enabled=False)

        param6 = arcpy.Parameter(
            displayName="Max",
            name="max",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input",
            enabled=False)

        param7 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3, param4, param5, param6, param7]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            parameters[7].value = _get_fields(parameters[0])
            parameters[1].value = None
            parameters[2].value = None
            parameters[3].enabled = False
            parameters[3].value = None
            parameters[4].enabled = False
            parameters[4].value = None
            parameters[5].enabled = False
            parameters[5].value = None
            parameters[6].enabled = False
            parameters[6].value = None

        if not parameters[1].hasBeenValidated and parameters[0].altered and parameters[7].valueAsText not in ["Failed to connect", "Invalid url"]:
            fields = json.loads(parameters[7].valueAsText)
            field = next((i for i in fields if i['name'] == parameters[1].valueAsText), None)
            if field is not None:
                if field['type'] == 'esriFieldTypeString':
                    parameters[2].filter.list = ['None', 'Coded Value']
                else:
                    parameters[2].filter.list = ['None', 'Coded Value', 'Range']

                if field['domain'] is not None:
                    parameters[3].value = field['domain']['name']
                    parameters[3].enabled = True
                    if 'codedValues' in field['domain']:
                        parameters[2].value = 'Coded Value'
                        coded_values = []
                        for value in field['domain']['codedValues']:
                            coded_values.append([value['code'],value['name']])
                        parameters[4].value = coded_values
                        parameters[4].enabled = True
                        parameters[5].enabled = False
                        parameters[6].enabled = False
                        parameters[5].value = None
                        parameters[6].value = None
                    else:
                        parameters[2].value = 'Range'
                        parameters[5].value = field['domain']['range'][0]
                        parameters[6].value = field['domain']['range'][1]
                        parameters[5].enabled = True
                        parameters[6].enabled = True
                        parameters[4].enabled = False
                        parameters[4].value = []                   
                else:
                    parameters[3].enabled = False
                    parameters[4].enabled = False
                    parameters[5].enabled = False
                    parameters[6].enabled = False
                    parameters[2].value = 'None'
                    parameters[3].value = None
                    parameters[4].value = []
                    parameters[5].value = None
                    parameters[6].value = None
                                
        elif not parameters[2].hasBeenValidated:
            if parameters[2].value == 'None':
                parameters[3].enabled = False
                parameters[4].enabled = False
                parameters[5].enabled = False
                parameters[6].enabled = False
            elif parameters[2].value == 'Coded Value':
                parameters[3].enabled = True 
                parameters[4].enabled = True
                parameters[5].enabled = False
                parameters[6].enabled = False
            elif parameters[2].value == 'Range':
                parameters[3].enabled = True  
                parameters[4].enabled = False
                parameters[5].enabled = True
                parameters[6].enabled = True

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if parameters[7].valueAsText == "Invalid URL":
            parameters[0].setErrorMessage("Input layer or table is not a hosted feature service")
        elif parameters[7].valueAsText == "Failed To Connect":
            parameters[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        else:
            parameters[0].clearMessage()
        return

    def execute(self, parameters, messages):
        field = arcpy.ListFields(parameters[0].valueAsText, parameters[1].valueAsText)[0]
        type = parameters[2].valueAsText
        name = parameters[3].valueAsText
        coded_values = parameters[4].value
        min = parameters[5].valueAsText
        max = parameters[6].valueAsText
        domain = None
        parameters[7].value = ''

        has_error = False
        if type == 'Coded Value':
            if len(coded_values) > 0:
                domain = {'type' : 'codedValue', 'name' : name, 'codedValues' : []}
                for row in coded_values:
                    code = row[0]
                    value = row[1]
            
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
            admin_url = _get_admin_url(parameters[0])
            if admin_url == "Invalid URL":
                raise Exception("Input layer or table is not a hosted feature service")
            elif admin_url == "Failed To Connect":
                raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
            token = arcpy.GetSigninToken()
            request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
            update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
            request_parameters['updateDefinition'] = json.dumps(update_defintion)
            resp = _url_request(admin_url + "/updateDefinition", request_parameters, token['referer'], request_type='POST')
        except Exception as e:
            arcpy.AddError("Failed to update domain: {0}".format(str(e)))

class AlterFieldAliasTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Alter Field Alias"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Layer or Table",
            name="input_table",
            datatype="GPTableView",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Field",
            name="field",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Alias",
            name="type",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            parameters[3].value = _get_fields(parameters[0])
            fields = json.loads(parameters[3].valueAsText)
            parameters[1].filter.list = [field['name'] for field in fields]
            parameters[1].value = None
            parameters[2].value = None

        if not parameters[1].hasBeenValidated and parameters[0].altered and parameters[3].valueAsText not in ["Failed to connect", "Invalid url"]:
            fields = json.loads(parameters[3].valueAsText)
            field = next((i for i in fields if i['name'] == parameters[1].valueAsText), None)
            if field is not None:
                parameters[2].value = field['alias']

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if parameters[3].valueAsText == "Invalid URL":
            parameters[0].setErrorMessage("Input layer or table is not a hosted feature service")
        elif parameters[3].valueAsText == "Failed To Connect":
            parameters[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        else:
            parameters[0].clearMessage()
        return

    def execute(self, parameters, messages):
        field = arcpy.ListFields(parameters[0].valueAsText, parameters[1].valueAsText)[0]
        alias = parameters[2].valueAsText
        parameters[3].value = ''
    
        try:
            admin_url = _get_admin_url(parameters[0])
            if admin_url == "Invalid URL":
                raise Exception("Input layer or table is not a hosted feature service")
            elif admin_url == "Failed To Connect":
                raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
            token = arcpy.GetSigninToken()
            request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
            update_defintion = {'fields' : [{'name' : field.name, 'alias' : alias}]}
            request_parameters['updateDefinition'] = json.dumps(update_defintion)
            resp = _url_request(admin_url + "/updateDefinition", request_parameters, token['referer'], request_type='POST')
        except Exception as e:
            arcpy.AddError("Failed to alter alias: {0}".format(str(e)))

class OpenWebMap(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Open Web Map"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Folder",
            name="folder",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Web Map",
            name="web_map",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="URL",
            name="url",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        param3 = arcpy.Parameter(
            displayName="Validation JSON",
            name="validation_json",
            datatype="GPString",
            parameterType="Derived",
            direction="Output")

        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if not parameters[0].hasBeenValidated:
            if not parameters[3].value:
                target = gis.GIS('pro')
                current_user = target.users.me    
                folders = current_user.folders  
                username = current_user.username     
                validation_json = { 'folders' : folders, 'username' : username }
                folders = sorted([folder['title'] for folder in folders])
                folders.insert(0, username)
                parameters[0].filter.list = folders
                parameters[3].value = json.dumps(validation_json)

        if not parameters[0].hasBeenValidated and parameters[0].value is not None:
            validation_json= json.loads(parameters[3].valueAsText)
            target = gis.GIS('pro')
            folder = parameters[0].valueAsText
            if folder == validation_json['username']:
                folder = None
            items = [item for item in target.users.me.items(folder) if item.type.lower() == "web map"] 
            validation_json['items'] = items
            parameters[3].value = json.dumps(validation_json)
            parameters[1].value = None
            parameters[1].filter.list = sorted([item.title for item in items])          

        if not parameters[1].hasBeenValidated and parameters[1].value is not None and parameters[0].value is not None:
            validation_json = json.loads(parameters[3].valueAsText)
            items = validation_json['items']
            webmap = next((item for item in items if item['title'] == parameters[1].valueAsText), None)
            if webmap is None:
                return
            url = "{0}home/webmap/viewer.html?webmap={1}".format(arcpy.GetActivePortalURL(), webmap['id'])
            parameters[2].value = url
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        try:
            url = parameters[2].valueAsText
            webbrowser.open(url)
            parameters[3].value = ''
        except Exception as e:
            arcpy.AddError("Failed to open url: {0}".format(str(e)))

#endregion

#region Solution Deployment and Download

class Group(object):
    """
    Represents the definition of a group within ArcGIS Online or Portal.
    """

    def __init__(self, info, thumbnail=None, portal_group=None):
        self.info = info
        self.thumbnail = thumbnail
        self.portal_group = portal_group

    def clone(self, connection, linked_folder=None):
        """Clone the group in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        linked_folder - The folder containing the associated solution items that will be shared with the new group"""
    
        try:
            new_group = None
            target = connection['target']
            original_group = self.info
        
            title = original_group['title']
            original_group['tags'].append("source-{0}".format(original_group['id']))
            if linked_folder:
                original_group['tags'].append("sourcefolder-{0}".format(linked_folder['id']))
            tags = ','.join(original_group['tags'])
    
            #Find a unique name for the group
            i = 1    
            while True:
                search_query = 'owner:{0} AND title:"{1}"'.format(connection['username'], title)
                groups = target.groups.search(search_query, outside_org=False)
                if len(groups) == 0:
                    break
                i += 1
                title = "{0} {1}".format(original_group['title'], i)
        
            new_group = target.groups.create(title, tags, original_group['description'], original_group['snippet'],
                                             'private', self.thumbnail, True, original_group['sortField'], original_group['sortOrder'], True)
            return new_group
        except Exception as e:
            raise ItemCreateException("Failed to create group '{0}': {1}".format(original_group['title'], str(e)), new_group)

    def write(self, items_directory):
        """Write the definition of the group to a local directory.
        Keyword arguments:
        items_directory - The items directory containing the definitions of the groups and items"""

        groupinfo_directory = os.path.join(items_directory, 'groupinfo')
        if not os.path.exists(groupinfo_directory):
            os.makedirs(groupinfo_directory)

        group_directory = os.path.join(groupinfo_directory, self.info['id'])
        if os.path.exists(group_directory):
            return None

        os.makedirs(group_directory)
        group_json = os.path.join(group_directory, 'groupinfo.json')
        with open(group_json, 'w') as file:
            file.write(json.dumps(self.info))

        thumbnail_directory = os.path.join(group_directory, 'thumbnail')
        os.makedirs(thumbnail_directory)
        thumbnail = self.portal_group.download_thumbnail(thumbnail_directory)
        if not thumbnail:
            os.rmdir(thumbnail_directory)

        return group_directory

class Item(object):
    """
    Represents the definition of an item within ArcGIS Online or Portal.
    """

    def __init__(self, info, data=None, sharing=None, thumbnail=None, portal_item=None):
        self.info = info
        self._data = data      
        self.sharing = sharing
        self.thumbnail = thumbnail
        self._item_property_names = ['title', 'type', 'description', 
                          'snippet', 'tags', 'culture',
                        'accessInformation', 'licenseInfo', 'typeKeywords']
        self.portal_item = portal_item

    @property
    def data(self):
        return copy.deepcopy(self._data)

    def _get_item_properties(self):
        """Get a dictionary of item properties used in create and update operations.
        Keyword arguments:
        extent - The extent to use in the item properties"""
        item_properties = {}
        for property_name in self._item_property_names:
            item_properties[property_name] = self.info[property_name]

        item_properties['typeKeywords'].append("source-{0}".format(self.info['id']))
        if TAG in item_properties['tags']:
            item_properties['tags'].remove(TAG)
            item_properties['typeKeywords'].append(TAG)
        item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])
        item_properties['tags'] = ','.join(item_properties['tags'])

        return item_properties

    def _share_new_item(self, new_item, group_mapping):
        """Share the new item using the based on sharing properties of original item and group mapping.
        Keyword arguments:
        new_item - The item to share
        group_mapping - A dictionary containing the id of the original group and the id of the new group"""
        if self.sharing:
            sharing = self.sharing
            everyone = sharing['access'] == 'everyone'
            org = sharing['access'] == 'org'
            groups = []
            for group in sharing['groups']:
                if group in group_mapping:
                    groups.append(group_mapping[group])
            new_item.share(everyone, org, ','.join(groups))

    def clone(self, connection, group_mapping, folder=None):  
        """Clone the item in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        folder - The folder to create the item in"""
    
        try:
            new_item = None
            original_item = self.info
            target = connection['target']
        
            # Get the item properties from the original item to be applied when the new item is created
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']
            item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))

            with tempfile.TemporaryDirectory() as temp_dir:
                data = self.data
                if not data and self.portal_item:
                    data = self.portal_item.download(temp_dir)
                 
                new_item = target.content.add(item_properties=item_properties, data=data, thumbnail=self.thumbnail, folder=folder['title'])

            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

    def write(self, items_directory):
        """Write the definition of the item to a local directory.
        Keyword arguments:
        items_directory - The items directory containing the definitions of the groups and items"""

        item_id = self.info['id']
        item_directory =  os.path.join(items_directory, item_id)
        if os.path.exists(item_directory):
            return None

        os.makedirs(item_directory)
        self.portal_item.download(item_directory)

        esriinfo_directory = os.path.join(item_directory, 'esriinfo')
        os.makedirs(esriinfo_directory)
        iteminfo_json = os.path.join(esriinfo_directory, 'iteminfo.json')
        with open(iteminfo_json, 'w') as file:
            file.write(json.dumps({'info' : self.info, 'sharing' : self.sharing }))
        
        thumbnail_directory = os.path.join(esriinfo_directory, 'thumbnail')
        os.makedirs(thumbnail_directory)
        thumbnail = self.portal_item.download_thumbnail(thumbnail_directory)
        if not thumbnail:
            os.rmdir(thumbnail_directory)

        return item_directory

class TextItem(Item):
    """
    Represents the definition of a text based item within ArcGIS Online or Portal.
    """

    def clone(self, connection, group_mapping, folder=None):  
        """Clone the item in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        folder - The folder to create the item in"""
    
        try:
            new_item = None
            original_item = self.info
            target = connection['target']
        
            # Get the item properties from the original item to be applied when the new item is created
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']
            item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))
            item_properties['text'] = self.data
            new_item = target.content.add(item_properties=item_properties, thumbnail=self.thumbnail, folder=folder['title'])

            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

    def write(self, items_directory):
        """Write the definition of the item to a local directory.
        Keyword arguments:
        items_directory - The items directory containing the definitions of the groups and items"""
        item_directory = Item.write(self, items_directory)
        if not item_directory:
            return None

        item_id = self.info['id']
        data_json = os.path.join(item_directory, item_id + '.json')
        with open(data_json, 'w') as file:
            file.write(json.dumps(self._data))

        return item_directory

class FeatureServiceItem(TextItem):
    """
    Represents the definition of a hosted feature service within ArcGIS Online or Portal.
    """

    def __init__(self, info, service_definition, layers_definition, features=None, data=None, sharing=None, thumbnail=None, portal_item=None):
        self._service_definition = json.loads(json.dumps(service_definition))
        self._layers_definition = json.loads(json.dumps(layers_definition))
        self.features = features
        super(TextItem, self).__init__(info, data, sharing, thumbnail, portal_item)

    @property
    def service_definition(self):
        return copy.deepcopy(self._service_definition)

    @property
    def layers_definition(self):
        return copy.deepcopy(self._layers_definition)

    def clone(self, connection, group_mapping, extent, folder=None):
        """Clone the feature service in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        extent - Default extent of the new feature service in WGS84
        folder - The folder to create the service in"""

        try:
            new_item = None
            original_item = self.info
            target = connection['target']       

            # Get the definition of the original feature service
            service_definition = self.service_definition

            # Create a new service from the definition of the original feature service
            for key in ['layers', 'tables', 'spatialReference', 'initialExtent', 'fullExtent', 'size']:
                if key in service_definition:
                    del service_definition[key]     
            service_definition['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))
            url = "{0}sharing/rest/content/users/{1}/".format(connection['url'], connection['username'])
            if folder:
                url += "{0}/".format(folder['id'])
            url += 'createService'
            request_parameters = {'f' : 'json', 'createParameters' : json.dumps(service_definition), 
                                  'outputType' : 'featureService', 'token' : connection['token']}
            resp = _url_request(url, request_parameters, connection['referer'], 'POST')
            new_item = target.content.get(resp['itemId'])        
    
            # Get the layer and table definitions from the original service
            layers_definition = self.layers_definition

            relationships = {} 
            for layer in layers_definition['layers'] + layers_definition['tables']:
                # Need to remove relationships first and add them back individually 
                # after all layers and tables have been added to the definition
                if 'relationships' in layer and len(layer['relationships']) != 0:
                    relationships[layer['id']] = layer['relationships']
                    layer['relationships'] = []

                # Need to remove all indexes duplicated for fields.
                # Services get into this state due to a bug in 10.4 and 1.2
                unique_fields = []
                if 'indexes' in layer:
                    for index in list(layer['indexes']):
                        fields = index['fields'].lower()
                        if fields in unique_fields:
                            layer['indexes'].remove(index)
                        else:
                            unique_fields.append(fields)
                
                # Set the extent of the feature layer to the specified default extent in web mercator
                layer['extent'] = extent['web_mercator']

            # Layers needs to come before Tables or it effects the output service
            definition = json.dumps(layers_definition, sort_keys=True) 
            new_fs_url = new_item.url

            # Add the layer and table defintions to the service
            find_string = "/rest/services"
            index = new_fs_url.find(find_string)
            admin_url = '{0}/rest/admin/services{1}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):])
            request_parameters = {'f' : 'json', 'addToDefinition' : definition, 'token' : connection['token']}
            _url_request(admin_url, request_parameters, connection['referer'], 'POST')

            # Add any releationship defintions back to the layers and tables
            for id in relationships:
                relationships_param = {'relationships' : relationships[id]}
                request_parameters = {'f' : 'json', 'addToDefinition' : json.dumps(relationships_param), 'token' : connection['token']}
                admin_url = '{0}/rest/admin/services{1}/{2}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):], id)
                _url_request(admin_url, request_parameters, connection['referer'], 'POST')

            # Update the item definition of the service
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']
            item_properties['text'] = self.data

            new_item.update(item_properties=item_properties, thumbnail=self.thumbnail)
    
            # Copy features from original item
            if self.features:
                for layer in new_item.layers + new_item.tables:
                    features = self.features[str(layer.properties['id'])]
                    chunk_size = 2000
                    for features_chunk in [features[i:i+chunk_size] for i in range(0, len(features), chunk_size)]:
                        layer.edit_features(adds=features_chunk)
                        
            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

    def write(self, items_directory):
        """Write the definition of the feature service to a local directory.
        Keyword arguments:
        items_directory - The items directory containing the definitions of the groups and items"""
        item_directory = TextItem.write(self, items_directory)
        if not item_directory:
            return None
        esriinfo_directory = os.path.join(item_directory, 'esriinfo')

        featureserver_json = os.path.join(esriinfo_directory, "featureserver.json")
        with open(featureserver_json, 'w') as file:
            file.write(json.dumps({'serviceDefinition' : self._service_definition, 'layersDefinition' : self._layers_definition}))

        if self.features:
            features_json = os.path.join(esriinfo_directory, "features.json")
            with open(features_json, 'w') as file:
                file.write(json.dumps(self.features))  

        return item_directory

class WebMapItem(TextItem):
    """
    Represents the definition of a web map within ArcGIS Online or Portal.
    """

    def clone(self, connection, group_mapping, service_mapping, extent, folder=None):  
        """Clone the web map in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        service_mapping - A data structure that contains the mapping between the original service item and url and the new service item and url
        extent - Default extent of the new web map in WGS84
        folder - The folder to create the web map in"""
    
        try:
            new_item = None
            original_item = self.info
            target = connection['target']
        
            # Get the item properties from the original web map which will be applied when the new item is created
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']
            item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))

            # Swizzle the item ids and URLs of the operational layers and tables in the web map
            webmap_json = self.data
            for service in service_mapping:
                url_pattern = re.compile(service[0][1], re.IGNORECASE)
                if 'operationalLayers' in webmap_json:
                    for layer in webmap_json['operationalLayers']:
                        if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                            if 'itemId' in layer:
                                if layer['itemId'].lower() == service[0][0]:
                                    layer['itemId'] = service[1][0]
                            if 'url' in layer:
                                layer['url'] = url_pattern.sub(service[1][1], layer['url'])
                if 'tables' in webmap_json:
                    for table in webmap_json['tables']:
                        if 'itemId' in table:
                            if table['itemId'].lower() == service[0][0]:
                                table['itemId'] = service[1][0]
                        if 'url' in table:
                            table['url'] = url_pattern.sub(service[1][1], table['url'])

            # Add the web map to the target portal
            item_properties['text'] = json.dumps(webmap_json)
            new_item = target.content.add(item_properties=item_properties, thumbnail=self.thumbnail, folder=folder['title'])

            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

class ApplicationItem(TextItem):
    """
    Represents the definition of an application within ArcGIS Online or Portal.
    """
    
    def clone(self, connection, group_mapping, service_mapping, webmap_mapping, folder=None):
        """Clone the application in the target orgnaization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        service_mapping - A data structure that contains the mapping between the original service item and url and the new service item and url
        webmap_mapping - Dictionary containing a mapping between the original web map id and new web map id
        folder - The folder to create the application in"""  
    
        try:
            new_item = None
            original_item = self.info
            target = connection['target']

            # Get the item properties from the original application which will be applied when the new item is created
            item_properties = self._get_item_properties()

            # Swizzle the item ids of the web maps, groups and URLs of defined in the application's data
            app_json = self.data
            app_json_text = ''

            if "Web AppBuilder" in original_item['typeKeywords']: #Web AppBuilder
                if 'portalUrl' in app_json:
                    app_json['portalUrl'] = connection['url']
                if 'map' in app_json:
                    if 'portalUrl' in app_json['map']:
                        app_json['map']['portalUrl'] = connection['url']
                    if 'itemId' in app_json['map']:
                        app_json['map']['itemId'] = webmap_mapping[app_json['map']['itemId']]
                if 'httpProxy' in app_json:
                    if 'url' in app_json['httpProxy']:
                        app_json['httpProxy']['url'] = connection['url'] + "sharing/proxy"
        
                app_json_text = json.dumps(app_json)        
                for service in service_mapping:
                    url_pattern = re.compile(service[0][1], re.IGNORECASE)
                    app_json_text = url_pattern.sub(service[1][1], app_json_text)
                item_properties['text'] = app_json_text

            elif original_item['type'] == "Operation View": #Operations Dashboard
                if 'widgets' in app_json:
                    for widget in app_json['widgets']:
                        if 'mapId' in widget:
                            widget['mapId'] = webmap_mapping[widget['mapId']]
                item_properties['text'] = json.dumps(app_json)

            else: #Configurable Application Template
                if 'folderId' in app_json:
                    app_json['folderId'] = folder['id']
                if 'values' in app_json:
                    if 'group' in app_json['values']:
                        app_json['values']['group'] = group_mapping[app_json['values']['group']]
                    if 'webmap' in app_json['values']:
                        app_json['values']['webmap'] = webmap_mapping[app_json['values']['webmap']]
                item_properties['text'] = json.dumps(app_json)

            # Add the application to the target portal
            new_item = target.content.add(item_properties=item_properties, thumbnail=self.thumbnail, folder=folder['title'])

            # Update the url of the item to point to the new portal and new id of the application
            if original_item['url']:
                find_string = "/apps/"
                index = original_item['url'].find(find_string)
                new_url = '{0}{1}'.format(connection['url'].rstrip('/'), original_item['url'][index:])
                find_string = "id="
                index = new_url.find(find_string)
                new_url = '{0}{1}'.format(new_url[:index + len(find_string)], new_item.id)
                item_properties = {'url' : new_url}
                new_item.update(item_properties)
    
            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

class ItemCreateException(Exception):
    """
    Exception raised during the creation of new items, used to clean-up any partially created items in the process.
    """
    pass

def _add_message(message, type='Info'):
    """Add a message to the output"""
    if type == 'Info':
        arcpy.AddMessage(message)
    elif type == 'Warning':
        arcpy.AddWarning(message)
    elif type == 'Error':
        arcpy.AddError(message)

def _get_solution_definition_portal(source, solution_item, solution_definition, deployed_items, copy_features, groups=[]):
    """Get the definition of the specified item. If it is a web application or webmap it will be called recursively find all the items that make up a given map or app.
    Keyword arguments:
    source - The portal containing the item
    solution_item - The item to get the definition from
    solution_definition - A list of item and group definitions that make up the solution
    deployed_items -  A list of item and group definitions that have already been retrieved in previous runs
    copy_features - A flag indicating if the data from the original feature services should be copied
    group - A list of groups to share the item with, used when the web application is based on a group of maps"""  

    # Check if the item has already been added to the collection
    existing_item = next((i for i in solution_definition if i.info['id'] == solution_item.id), None)
    if existing_item:
        return

    deployed_item = next((i for i in deployed_items if i.info['id'] == solution_item.id), None)
    solution_definition.append(deployed_item)

    # If the item is an application or dashboard find the web map or group that the application is built from
    if solution_item['type'] in ['Web Mapping Application','Operation View']:
        if deployed_item:
            app_json = deployed_item.data
        else:
            app_json = solution_item.get_data()
            solution_definition.append(ApplicationItem(solution_item, data=app_json, sharing={
				    "access": "private",
				    "groups": groups
					    }, thumbnail=solution_item.get_thumbnail_link(), portal_item=solution_item))
   
        webmap_id = None
        if solution_item['type'].lower() == "operation view": #Operations Dashboard
            if 'widgets' in app_json:
                for widget in app_json['widgets']:
                    if 'mapId' in widget:
                        webmap_id = widget['mapId']
                        break

        elif "Web AppBuilder" in solution_item['typeKeywords']: #Web AppBuilder
            if 'map' in app_json:
                if 'itemId' in app_json['map']:
                    webmap_id = app_json['map']['itemId']

        else: #Configurable Application Template
            if 'values' in app_json:
                if 'group' in app_json['values']:
                    group_id = app_json['values']['group']
                    group = next((g for g in solution_definition if g.info['id'] == group_id), None)
                    if not group:
                        deployed_group = next((i for i in deployed_items if i.info['id'] == group_id), None)
                        if deployed_group:
                            group = deployed_group.portal_group
                            solution_definition.append(deployed_group)
                        else:
                            group = source.groups.get(group_id)
                            id = group.id # Bug, thumbnail is not returned properly unless we request another property from the object
                            solution_definition.append(Group(group, thumbnail=group.get_thumbnail_link(), portal_group=group))
                    
                    search_query = 'group:{0} AND type:{1}'.format(group_id, 'Web Map')
                    group_items = source.content.search(search_query, max_items=100, outside_org=True)
                    for webmap in group_items:
                        _get_solution_definition_portal(source, webmap, solution_definition, deployed_items, copy_features, [group_id])

                if 'webmap' in app_json['values']:
                    webmap_id = app_json['values']['webmap']
        
        if webmap_id:
            deployed_webmap = next((i for i in deployed_items if i.info['id'] == webmap_id), None)
            if deployed_webmap:
                webmap = deployed_webmap.portal_item
            else:
                webmap = source.content.get(webmap_id)
            _get_solution_definition_portal(source, webmap, solution_definition, deployed_items, copy_features)

    # If the item is a web map find all the feature service layers and tables that make up the map
    elif solution_item['type'] == 'Web Map':
        if deployed_item:
            webmap_json = deployed_item.data
        else:    
            webmap_json = solution_item.get_data()
            solution_definition.append(WebMapItem(solution_item, data=webmap_json, sharing={
				    "access": "private",
				    "groups": groups
					    }, thumbnail=solution_item.get_thumbnail_link(), portal_item=solution_item))
        
        if 'operationalLayers' in webmap_json:
            for layer in webmap_json['operationalLayers']:
                if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                    if 'itemId' in layer:
                        deployed_service = next((i for i in deployed_items if i.info['id'] == layer['id']), None)
                        if deployed_service:
                            feature_service = deployed_service.portal_item
                        else:
                            feature_service = source.content.get(layer['itemId'])
                        _get_solution_definition_portal(source, feature_service, solution_definition, deployed_items, copy_features)

        if 'tables' in webmap_json:
            for table in webmap_json['tables']:
                    if 'itemId' in table:
                        deployed_service = next((i for i in deployed_items if i.info['id'] == table['id']), None)
                        if deployed_service:
                            feature_service = deployed_service.portal_item
                        else:
                            feature_service = source.content.get(table['itemId'])
                        _get_solution_definition_portal(source, feature_service, solution_definition, deployed_items, copy_features)

    # If the item is a feature service get the definition of the service and its layers and tables
    elif solution_item['type'] == 'Feature Service':
        if not deployed_item:
            url = solution_item['url']
            svc = lyr.Service(url, source)
            service_definition = svc.definition

            # Need to serialize the item before getting the layer definitions
            iteminfo = json.loads(json.dumps(solution_item))

            # Get the defintions of the the layers and tables
            layers_definition = { 'layers' : [], 'tables' : [] }
            for layer in solution_item.layers:
                layers_definition['layers'].append(layer.properties)
            for table in solution_item.tables:
                layers_definition['tables'].append(table.properties)
        
            # Get the data associated with the item 
            data = solution_item.get_data()     
        
            # Get the features for the layers and tables if requested
            features = None
            if copy_features:
                features = {}
                for layer in solution_item.layers + solution_item.tables:
                    features[str(layer.properties['id'])] = _get_features(layer)

            solution_definition.append(FeatureServiceItem(iteminfo, service_definition, layers_definition, features=features, data=data, sharing= {
				        "access": "private",
				        "groups": groups
					        }, thumbnail=solution_item.get_thumbnail_link(), portal_item=solution_item))

    # All other item types
    else:
        if not deployed_item:
            if solution_item['type'] in TEXT_BASED_ITEM_TYPES:
                item_definition['data'] = solution_item.get_data()
                solution_definition.append(TextItem(solution_item, data=solution_item.get_data(), sharing={
			    "access": "private",
			    "groups": groups
			        }, thumbnail=solution_item.get_thumbnail_link(), portal_item=solution_item))
            else:
                solution_definition.append(Item(solution_item, data=None, sharing={
			    "access": "private",
			    "groups": groups
			        }, thumbnail=solution_item.get_thumbnail_link(), portal_item=solution_item))

def _get_solution_definition_local(source_directory, solution, solution_definition, deployed_items, copy_features):
    """Get the definition of the solution. This may be made up of multiple items and groups.
    Keyword arguments:
    source_directory - The directory containing the items and the SolutionDefinition.json file that defines the items that make up a given solution.
    solution - The name of the solution to get the definitions for.
    solution_items - A list of item and group definitions that make up the solution
    deployed_items -  A list of item and group definitions that have already been retrieved in previous runs
    copy_features - A flag indicating if the data from the original feature services should be copied"""  

    # Read the SolutionDefinitions.json file to get the IDs of the items and groups that make up the solution
    solutions_definition_file = os.path.join(source_directory, 'SolutionDefinitions.json') 
    definitions = None
    if os.path.exists(solutions_definition_file):
        with open(solutions_definition_file, 'r') as file:
            content = file.read() 
            definitions = json.loads(content)
    
    if not definitions:
        raise Exception("Source directory does not contain a valid SolutionDefinitions configuration file")

    if solution not in definitions['Solutions']:
        raise Exception("The SolutionDefinitions configuration file does not contain a definition for {0}".format(solution))

    # Get the definition of each item defined within the solution
    for item_id in definitions['Solutions'][solution]['items']:
        deployed_item = next((i for i in deployed_items if i.info['id'] == item_id), None)
        if deployed_item:
            solution_definition.append(deployed_item)
            continue

        item_directory = os.path.join(source_directory, item_id)
        if not os.path.exists(item_directory):
            raise Exception("Item: {0} was not found of the source directory".format(item_id))

        solution_item = None

        # Find the data of the item or the first file found under the item directory
        data = next((os.path.join(item_directory, f) for f in os.listdir(item_directory) if os.path.isfile(os.path.join(item_directory, f))),None)

        # Find and read the iteminfo file which describe the item
        esriinfo_directory = os.path.join(item_directory, 'esriinfo')
        iteminfo = os.path.join(esriinfo_directory, 'iteminfo.json')
        with open(iteminfo, 'r') as file:
            content = file.read() 
            item = json.loads(content)
        
        # Create the correct item depending on the type definied in the item info
        type = item['info']['type']
        if type in TEXT_BASED_ITEM_TYPES:
            with open(data, 'r') as file:
                content = file.read() 
                data = json.loads(content)
            if type == 'Feature Service':
                featureserver_json = None
                features_json = None
                featureserver_file = os.path.join(esriinfo_directory, 'featureserver.json')
                with open(featureserver_file, 'r') as file:
                    featureserver_json = json.loads(file.read())
                if copy_features:
                    features_file = os.path.join(esriinfo_directory, 'features.json')
                    if os.path.exists(features_file):
                        with open(features_file, 'r') as file:
                            features_json = json.loads(file.read())

                solution_item = FeatureServiceItem(item['info'], featureserver_json['serviceDefinition'], featureserver_json['layersDefinition'], features=features_json, data=data, sharing=item['sharing'])

            elif type == 'Web Map':
                solution_item = WebMapItem(item['info'], data, item['sharing'])
            elif type in ['Web Mapping Application', 'Operation View']:
                solution_item = ApplicationItem(item['info'], data, item['sharing'])
            else:
                solution_item = TextItem(item['info'], data, item['sharing'])
        else:
            solution_item = Item(item['info'], data, item['sharing'])

        # If the item has a thumbnail find the path
        thumbnail_directory = os.path.join(esriinfo_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_item.thumbnail = thumbnail

        # Append the item to the list
        solution_definition.append(solution_item)

    # Get the definition of each group defined within the solution
    for group_id in definitions['Solutions'][solution]['groups']:
        deployed_item = next((i for i in deployed_items if i.info['id'] == group_id), None)
        if deployed_item:
            solution_definition.append(deployed_item)
            continue

        group_directory = os.path.join(source_directory, 'groupinfo', group_id)
        if not os.path.exists(group_directory):
            raise Exception("Group: {0} was not found of the groupinfo under the source directory".format(group_id))

        # Find and read the groupinfo file which describe the group
        solution_group = None
        groupinfo = os.path.join(group_directory, 'groupinfo.json')
        with open(groupinfo, 'r') as file:
            content = file.read() 
            group = json.loads(content)
            solution_group = Group(group)

        # If the group has a thumbnail find the path
        thumbnail_directory = os.path.join(group_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_group.thumbnail = thumbnail

        # Append the group to the list
        solution_definition.append(solution_group)

def _get_features(feature_layer):
    """Get the features for the given feature layer of a feature service. Returns a list of json features.
    Keyword arguments:
    feature_layer - The feature layer to return the features for"""  
    total_features = []
    record_count = feature_layer.query(returnCountOnly = True)
    max_record_count = feature_layer.properties['maxRecordCount']
    if max_record_count < 1:
        max_record_count = 1000
    offset = 0
    while offset < record_count:
        features = feature_layer.query(as_json=True, outSR=102100, resultOffset=offset, resultRecordCount=max_record_count)['features']
        offset += len(features)
        total_features += features
    return total_features

def _get_existing_item(item, folder_items):
    """Test if an item with a given source tag already exists in the collection of items within a given folder. 
    This is used to determine if the item has already been cloned in the folder.
    Keyword arguments:
    item - The original item used to determine if it has already been cloned to the specified folder.
    folder_items - A list of items from a given folder used to search if the item has already been cloned."""  
   
    return next((folder_item for folder_item in folder_items if folder_item['type'] == item['type'] 
                          and "source-{0}".format(item['id']) in folder_item['typeKeywords']), None)

def _get_existing_group(connection, group, linked_folder):
    """Test if a group with a given source tag already exists in the organization. 
    This is used to determine if the group has already been created and if new maps and apps that belong to the same group should be shared to the same group.
    Keyword arguments:
    group - The original group used to determine if it has already been cloned in the orgnaization.
    linked_folder - The folder in which new items are created. Each group is tied to a given folder and when applicable the items in that folder are shared with the associated group.""" 
    
    target = connection['target']
    search_query = 'owner:{0} AND tags:"source-{1},sourcefolder-{2}"'.format(connection['username'], group['id'], linked_folder['id']) 
    groups = target.groups.search(search_query, outside_org=False)
    if len(groups) > 0:
        return groups[0]
    return None

def _download_solutions(connection, solution_group, solutions, copy_features, output_directory):
    """Download solutions from a portal to a local directory
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    solution_group - The name of the group of solutions
    solutions - A list of solutions to be cloned into the portal
    copy_features - A flag indicating if the data from the original feature services should be downloaded as well
    output_directory - The directory to write the solution items and the definition configuration file""" 
    
    target = connection['target']
    deployed_items = []

    for solution in solutions:
        try:
            download_message = 'Downloading {0}'.format(solution)
            _add_message(download_message)
            arcpy.SetProgressor('default', download_message) 

            # Search for the map or app in the given organization using the map or app name and a specific tag
            search_query = 'tags:"{0},solution.{1}" AND title:"{2}"'.format(TAG, solution_group, solution)
            items = target.content.search(search_query, outside_org=True)
            solution_item = next((item for item in items if item.title == solution), None)
            if not solution_item:
                continue

            # Get the definitions of the groups and items (maps, services in the case of an spplication) that make up the solution
            solution_definition = []
            _get_solution_definition_portal(target, solution_item, solution_definition, deployed_items, copy_features)

            # Set the progressor
            item_count = len(solution_definition)
            arcpy.SetProgressor('step', download_message, 0, item_count, 1)

            # Create the output directory if it doesn't already exist
            if not os.path.exists(output_directory):
                os.makedirs(output_directory)

            # Write the items to the output directory
            for item in [item for item in solution_definition if isinstance(item, Item)]:
                item_directory = item.write(output_directory)
                if item_directory:
                    _add_message("Downloaded {0} {1}".format(item.info['type'], item.info['title']))
                else:
                    _add_message("Existing {0} {1} already downloaded".format(item.info['type'], item.info['title']))
                arcpy.SetProgressorPosition() 

            # Write the groups to the output directory
            for group in [group for group in solution_definition if isinstance(group, Group)]:
                group_directory = group.write(output_directory)
                if group_directory:
                    _add_message("Downloaded Group {0}".format(group.info['title']))
                else:
                    _add_message("Existing Group {0} already downloaded".format(group.info['title']))
                arcpy.SetProgressorPosition() 

            # Update the solution definitions configuration file with the new items that have been downloaded
            solutions_definition_file = os.path.join(output_directory, 'SolutionDefinitions.json') 
            if not os.path.exists(solutions_definition_file):
                file = open(solutions_definition_file, "w")
                file.close
    
            with open(solutions_definition_file, 'r+') as file:
                content = file.read()  
                file.seek(0)   
                definitions = {'Solution Groups' : {}, 'Solutions' : {} }
                if not content == '':
                    definitions = json.loads(content)

                if solution_group not in definitions['Solution Groups']:
                    definitions['Solution Groups'][solution_group] = []

                if solution not in definitions['Solution Groups'][solution_group]:
                    definitions['Solution Groups'][solution_group].append(solution)

                definitions['Solutions'][solution] = {'items' : [], 'groups' : []}

                for item in [item for item in solution_definition if isinstance(item, Item)]:
                    definitions['Solutions'][solution]['items'].append(item.info['id'])

                for group in [group for group in solution_definition if isinstance(group, Group)]:
                    definitions['Solutions'][solution]['groups'].append(group.info['id'])

                file.write(json.dumps(definitions))
                file.truncate()

            # Everything has been successfully downloaded, add the list of items to the list of items that have been deployed during the entire run
            deployed_items = list(set(deployed_items + solution_definition))
            _add_message('Successfully downloaded {0}'.format(solution))
            _add_message('------------------------')
        except Exception as e:
            _add_message('Failed to download {0}: {1}'.format(solution, str(e)), 'Error')
            _add_message('------------------------')

def _create_solutions(connection, solution_group, solutions, extent, copy_features, output_folder):
    """Clone solutions into a new portal
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    solution_group - The name of the group of solutions
    solutions - A list of solutions to be cloned into the portal
    extent - The default extent of the new maps and services in WGS84
    copy_features - A flag indicating if the data from the original feature services should be copied as well
    output_folder - The name of the folder to create the new items within the user's content""" 

    target = connection['target']
    if connection['local']:
        source_directory = connection['source directory']
    else:
        source = gis.GIS()

    group_mapping = {}   
    service_mapping = []
    webmap_mapping = {}
    deployed_items = []
    
    # If the folder does not already exist create a new folder
    current_user = target.users.me
    folders = current_user.folders
    folder = next((folder for folder in folders if folder['title'] == output_folder), None)
    if not folder:
        folder = target.content.create_folder(output_folder)
    
    # Get the all items in the folder
    folder_items = current_user.items(folder['title'])

    for solution in solutions:
        try:
            deploy_message = 'Deploying {0}'.format(solution)
            _add_message(deploy_message)
            arcpy.SetProgressor('default', deploy_message) 
                      
            created_items = []
            solution_definition = []           

            if connection['local']:
                # Get the definitions of the items and groups that make up the solution
                _get_solution_definition_local(source_directory, solution, solution_definition, deployed_items, copy_features)
            else:
                # Search for the map or app in the given organization using the map or app name and a specific tag
                search_query = 'accountid:{0} AND tags:"{1},solution.{2}" AND title:"{3}"'.format(PORTAL_ID, TAG, solution_group, solution)
                items = source.content.search(search_query)
                solution_item = next((item for item in items if item.title == solution), None)
                if not solution_item:
                    _add_message("Failed to find original item {0}".format(solution), 'Error')
                    _add_message('------------------------')
                    continue

                # Check if the item has already been cloned into the target portal and if so, continue on to the next map or app.
                existing_item = _get_existing_item(solution_item, folder_items)
                if existing_item:
                    _add_message("{0} already exists in {1} folder".format(solution_item.title, folder['title']))
                    _add_message('------------------------')
                    continue

                # Get the definitions of the items and groups that make up the solution
                _get_solution_definition_portal(source, solution_item, solution_definition, deployed_items, copy_features)

            # Set the progressor
            item_count = len(solution_definition)
            arcpy.SetProgressor('step', deploy_message, 0, item_count, 1)

            # Create a copy of the list referencing the original solution items so they don't need to be fetched again future loops
            original_solution_items = list(solution_definition)

            # Clone the groups
            for group in [group for group in solution_definition if isinstance(group, Group)]:
                solution_definition.remove(group)
                original_group = group.info

                if original_group['id'] in group_mapping: #We have already found or created this item
                    _add_message("Existing Group {0} found".format(original_group['title']))
                    arcpy.SetProgressorPosition()
                    continue
                
                new_group = _get_existing_group(connection, original_group, folder)
                if not new_group:
                    new_group = group.clone(connection, folder)
                    created_items.append(new_group)
                    _add_message("Created Group {0}".format(new_group['title']))
                else:
                    _add_message("Existing Group {0} found".format(new_group['title']))
                group_mapping[original_group['id']] = new_group['id']
                arcpy.SetProgressorPosition()

            # Clone the feature services
            for feature_service in [item for item in solution_definition if isinstance(item, FeatureServiceItem)]:
                solution_definition.remove(feature_service)
                original_item = feature_service.info

                if original_item['id'] in [service_map[0][0] for service_map in service_mapping]: #We have already found or created this item
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title'])) 
                    arcpy.SetProgressorPosition()
                    continue

                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:                     
                    new_item = feature_service.clone(connection, group_mapping, extent, folder)
                    created_items.append(new_item)
                    _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
                else:
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))        
                service_mapping.append([(original_item['id'], original_item['url']),
                                            (new_item['id'], new_item['url'])])
                arcpy.SetProgressorPosition()

            # Clone the web maps
            for webmap in [item for item in solution_definition if isinstance(item, WebMapItem)]:
                solution_definition.remove(webmap)
                original_item = webmap.info

                if original_item['id'] in webmap_mapping: #We have already found or created this item
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))   
                    arcpy.SetProgressorPosition()
                    continue
          
                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:
                    new_item = webmap.clone(connection, group_mapping, service_mapping, extent, folder)
                    created_items.append(new_item)
                    _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
                else:
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))   
                webmap_mapping[original_item['id']] =  new_item['id']
                arcpy.SetProgressorPosition()

            # Clone the applications
            for application in [item for item in solution_definition if isinstance(item, ApplicationItem)]:
                solution_definition.remove(application)
                original_item = application.info

                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:                   
                    new_item = application.clone(connection, group_mapping, service_mapping, webmap_mapping, folder)
                    created_items.append(new_item)
                    _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
                else:
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title'])) 
                arcpy.SetProgressorPosition()
            
            # Clone all other items
            for item in solution_definition:
                original_item = item.info

                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:                   
                    new_item = item.clone(connection, group_mapping, folder)
                    created_items.append(new_item)
                    _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
                else:
                    _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title'])) 
                arcpy.SetProgressorPosition()             

            # Everything has been successfully cloned, add the list of items to the list of items that have been deployed during the entire run
            deployed_items = list(set(deployed_items + original_solution_items))
            _add_message('Successfully added {0}'.format(solution))
            _add_message('------------------------')

        except Exception as e:
            if type(e) == ItemCreateException:
                _add_message(e.args[0], 'Error')
                if e.args[1]:
                    created_items.append(e.args[1])
            else:
                _add_message(str(e), 'Error')

            for solution_item in created_items:
                if solution_item.delete():
                    _add_message("Deleted {0}".format(solution_item.title))
            _add_message('Failed to add {0}'.format(solution), 'Error')
            _add_message('------------------------')

#endregion

#region Tools and Validation Helpers

def _url_request(url, request_parameters, referer=None, request_type='GET', repeat=0, raise_on_failure=True):
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

def _get_fields(parameter):
    admin_url = _get_admin_url(parameter)
    if admin_url in ["Invalid URL", "Failed To Connect"]:
        return admin_url

    try:      
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'] }
        resp = _url_request(admin_url, request_parameters, token['referer'])
        
        if "serviceItemId" not in resp:
            return "Failed To Connect"

        return json.dumps(resp['fields'])
    except:
        return "Failed To Connect"

def _get_admin_url(parameter):
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

def _get_default_extent(extent):   
    coordinates = []
    sr = None

    if extent:
        default_extent = {'xmin' : extent.XMin, 'xmax' : extent.XMax, 'ymin' : extent.YMin, 'ymax' : extent.YMax }
        sr = extent.spatialReference
    else: # Get the default extent defined in the portal
        portal_description = json.loads(arcpy.GetPortalDescription())
        default_extent = portal_description['defaultExtent']
        sr = arcpy.SpatialReference(default_extent['spatialReference']['wkid'])
       
    coordinates = [[default_extent['xmin'], default_extent['ymin']], 
        [default_extent['xmax'], default_extent['ymin']], 
        [default_extent['xmax'], default_extent['ymax']], 
        [default_extent['xmin'], default_extent['ymax']], 
        [default_extent['xmin'], default_extent['ymin']]]
    polygon = arcpy.Polygon(arcpy.Array([arcpy.Point(*coords) for coords in coordinates]), sr)
    extent = polygon.extent

    # Project the extent to WGS84 which is used by default for the web map and services initial extents
    extent_wgs84 = extent.projectAs(arcpy.SpatialReference(4326))
    extent_web_mercator = extent.projectAs(arcpy.SpatialReference(102100))
    extent_dict = {'wgs84' : '{0},{1},{2},{3}'.format(extent_wgs84.XMin, extent_wgs84.YMin, 
                                                extent_wgs84.XMax, extent_wgs84.YMax),
                  'web_mercator' : {
				    "xmin" : extent_web_mercator.XMin,
				    "ymin" : extent_web_mercator.YMin,
				    "xmax" : extent_web_mercator.XMax,
				    "ymax" : extent_web_mercator.YMax,
				    "spatialReference" : {
					    "wkid" : 102100 } } }

    return extent_dict

#endregion
