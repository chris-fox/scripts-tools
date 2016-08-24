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
import arcpy, json, uuid, re, tempfile, os, copy, webbrowser
from arcgis import gis, lyr

PORTAL_ID = 'WmoCHIxoWP90bCkH' #http://arcgissolutionsdeploymentdev.maps.arcgis.com/
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
        self.tools = [DeploySolutionsTool, CloneItemsTool, UpdateDomainTool, AlterFieldAliasTool, OpenWebMap]

class DeploySolutionsTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Deploy Solutions"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Industry",
            name="industry",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Initiative",
            name="initiative",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Solution",
            name="solution",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param3 = arcpy.Parameter(
            displayName="Folder",
            name="folder",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Copy Sample Data",
            name="copy_sample_data",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param4.value = False

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
                groups = source.groups.search(search_query, outside_org=False)
                solutions = {}
                for group in groups:
                    solutions[group['title']] = {'id' : group['id'], 'solution_groups' : None}
                parameters[0].filter.list = sorted([group['title'] for group in groups])

                target = gis.GIS('pro')
                folders = target.users.me.folders
                parameters[3].filter.list = sorted([folder['title'] for folder in folders])
                validation_json =  { 'solutions' : solutions, 'folders' : folders }
                parameters[5].value = json.dumps(validation_json)

            if parameters[0].value:
                validation_json = json.loads(parameters[5].value)
                industry = parameters[0].valueAsText
                if not validation_json['solutions'][industry]['solution_groups']:
                    source = gis.GIS()
                    search_query = 'group:{0}'.format(validation_json['solutions'][industry]['id'])
                    items = source.content.search(search_query, max_items=1000)
                    tag_prefix = 'solution.'
                    solutions = {}
                    for item in items:
                        for solution_group in [tag[len(tag_prefix):] for tag in item.tags if tag.startswith('solution.')]:
                            if solution_group not in solutions:
                                solutions[solution_group] = []
                            solutions[solution_group].append(item.title)
                    parameters[1].filter.list = sorted([solution_group for solution_group in solutions])
                    validation_json['solutions'][industry]['solution_groups'] = solutions
                    parameters[5].value = json.dumps(validation_json)
                else:
                    parameters[1].filter.list = sorted([solution_group for solution_group in validation_json['solutions'][industry]['solution_groups']])
            parameters[1].value = None

        if parameters[0].value and not parameters[1].hasBeenValidated and parameters[1].value:
            validation_json = json.loads(parameters[5].valueAsText)  
            solutions = validation_json['solutions']
            industry = parameters[0].valueAsText   
            solution_group = parameters[1].valueAsText
            items = solutions[industry]['solution_groups'][solution_group]
            parameters[2].filter.list = sorted(items)
            parameters[2].value = arcpy.ValueTable()

        if not parameters[3].hasBeenValidated:
            validation_json = json.loads(parameters[5].valueAsText)  
            folders = validation_json['folders']
            if parameters[3].value:
                parameters[3].filter.list = sorted(set([parameters[3].valueAsText] + [folder['title'] for folder in folders]))
            else:
                parameters[3].filter.list = sorted([folder['title'] for folder in folders])

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        target = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

        if not target:
            return             
        
        source = gis.GIS()

        # Get the input parameters
        industry = parameters[0].valueAsText
        solution_group = parameters[1].valueAsText
        value_table = parameters[2].value
        solutions = []
        for i in range(0, value_table.rowCount):
            solution = value_table.getValue(i, 0)
            if solution not in solutions:
                solutions.append(solution)       
        output_folder = parameters[3].valueAsText
        copy_data = parameters[4].value
        parameters[5].value = ''
    
        for solution in solutions:
            deploy_message = 'Deploying {0}'.format(solution)
            _add_message(deploy_message)
            arcpy.SetProgressor('default', deploy_message)                           

            # Search for the industry group
            search_query = 'accountid:{0} AND tags:"{1}" AND title:"{2}"'.format(PORTAL_ID, TAG, industry)
            groups = source.groups.search(search_query)
            if len(groups) == 0:
                _add_message("Failed to find group {0} in the source organization".format(industry), 'Error')
                _add_message('------------------------')
                continue

            # Search for the solution the source organization within the industry group using the title of the item.
            search_query = 'accountid:{0} AND group:"{1}" AND title:"{2}"'.format(PORTAL_ID, groups[0]['id'], solution)
            items = source.content.search(search_query)
            solution_item = next((item for item in items if item.title == solution), None)
            if not solution_item:
                _add_message("Failed to find solution {0}".format(solution), 'Error')
                _add_message('------------------------')
                continue

            clone_item(target, solution_item, output_folder, None, copy_data)

class CloneItemsTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Clone Items"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Items",
            name="items",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param1 = arcpy.Parameter(
            displayName="Folder",
            name="folder",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Area of Interest",
            name="area_of_interest",
            datatype="GPExtent",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Copy Data",
            name="copy_data",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param3.value = False

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
            if not parameters[4].value:
                target = gis.GIS('pro')
                folders = target.users.me.folders
                parameters[1].filter.list = sorted([folder['title'] for folder in folders])
                validation_json =  { 'folders' : folders }
                parameters[4].value = json.dumps(validation_json)

        if not parameters[1].hasBeenValidated:
            validation_json = json.loads(parameters[4].valueAsText)  
            folders = validation_json['folders']
            if parameters[1].value:
                parameters[1].filter.list = sorted(set([parameters[1].valueAsText] + [folder['title'] for folder in folders]))
            else:
                parameters[1].filter.list = sorted([folder['title'] for folder in folders])

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        target = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")
        
        if not target:
            return             
        
        source = gis.GIS()

        # Get the input parameters
        value_table = parameters[0].value
        item_ids = []
        for i in range(0, value_table.rowCount):
            item_id = value_table.getValue(i, 0)
            if item_id not in item_ids:
                item_ids.append(item_id)   
        output_folder = parameters[1].valueAsText
        extent = parameters[2].value
        copy_data = parameters[3].value
        parameters[4].value = ''

        for item_id in item_ids:
            try:
                item = source.content.get(item_id)
            except RuntimeError as e:
                _add_message("Failed to get item {0}: {1}".format(item_id, str(e)), 'Error')
                _add_message('------------------------')
                continue

            deploy_message = 'Cloning {0}'.format(item['title'])
            _add_message(deploy_message)
            arcpy.SetProgressor('default', deploy_message)                           

            clone_item(target, item, output_folder, extent, copy_data)

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
            extent = parameters[3].value
            copy_features = parameters[4].value
            output_folder = parameters[5].valueAsText
            parameters[6].value = ''
                            
            # Clone the solutions
            clone_item(connection, solution_group, solutions, extent, copy_features, output_folder)
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
        target = None
        try:
            # Setup the target portal using the active portal within Pro
            target = gis.GIS('pro')
        except Except:
            arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

        if not target:
            return             
        
        solution_group = parameters[0].valueAsText
        value_table = parameters[1].value
        solutions = [value_table.getValue(i, 0) for i in range(0, value_table.rowCount)]
        solutions = sorted(list(set(solutions)))
        copy_data = parameters[2].value
        output_directory = parameters[3].valueAsText
        parameters[4].value = ''

        cached_items = []

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
                item_definitions = []
                _get_item_definitions(solution_item, item_definitions, cached_items, copy_data)

                # Add the items to the cached list so they can be reused if items are reused in other solutions
                cached_items = list(set(cached_items + item_definitions))

                # Create the output directory if it doesn't already exist
                if not os.path.exists(output_directory):
                    os.makedirs(output_directory)

                if download_items(item_definitions, output_directory):
                    _add_message('Successfully downloaded {0}'.format(solution))
                    _add_message('------------------------')
            except Exception as e:
                _add_message('Failed to download {0}: {1}'.format(solution, str(e)), 'Error')
                _add_message('------------------------')

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

            for item in [item for item in item_definitions if isinstance(item, ItemDefinition)]:
                definitions['Solutions'][solution]['items'].append(item.info['id'])

            for group in [group for group in item_definitions if isinstance(group, GroupDefinition)]:
                definitions['Solutions'][solution]['groups'].append(group.info['id'])

            file.write(json.dumps(definitions))
            file.truncate()

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
            feature_layer = _get_feature_layer(parameters[0])
            if feature_layer == "Invalid URL":
                raise Exception("Input layer or table is not a hosted feature service")
            elif feature_layer == "Failed To Connect":
                raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
            update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
            feature_layer.admin.update_definition(update_defintion)
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
            feature_layer = _get_feature_layer(parameters[0])
            if feature_layer == "Invalid URL":
                raise Exception("Input layer or table is not a hosted feature service")
            elif feature_layer == "Failed To Connect":
                raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
            update_defintion = {'fields' : [{'name' : field.name, 'alias' : alias}]}
            feature_layer.admin.update_definition(update_defintion)
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

#region Group and Item Definition Classes

class GroupDefinition(object):
    """
    Represents the definition of a group within ArcGIS Online or Portal.
    """

    def __init__(self, info, thumbnail=None, portal_group=None):
        self.info = info
        self.thumbnail = thumbnail
        self.portal_group = portal_group

    def clone(self, target, linked_folder=None):
        """Clone the group in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        linked_folder - The folder containing the associated solution items that will be shared with the new group"""
    
        try:
            new_group = None
            original_group = self.info
            
            title = original_group['title']
            tags = original_group['tags']
            for tag in list(tags):
                if tag.startswith("source-") or tag.startswith("sourcefolder-"):
                    tags.remove(tag)
         
            original_group['tags'].append("source-{0}".format(original_group['id']))
            if linked_folder:
                original_group['tags'].append("sourcefolder-{0}".format(linked_folder['id']))
            tags = ','.join(original_group['tags'])
            
            #Find a unique name for the group
            i = 1    
            while True:
                search_query = 'title:"{0}"'.format(title)
                groups = [group for group in target.groups.search(search_query, outside_org=False) if group['title'] == title]
                if len(groups) == 0 :
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

class ItemDefinition(object):
    """
    Represents the definition of an item within ArcGIS Online or Portal.
    """

    def __init__(self, info, data=None, sharing=None, thumbnail=None, portal_item=None):
        self.info = info
        self._data = data    
        self.sharing = sharing
        if not self.sharing:
            self.sharing = {
				"access": "private",
				"groups": []
					}
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

        typeKeywords = item_properties['typeKeywords']
        for keyword in list(typeKeywords):
            if keyword.startswith("source-"):
                typeKeywords.remove(keyword)

        typeKeywords.append("source-{0}".format(self.info['id']))
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

    def clone(self, target, extent=None, group_mapping={}, folder=None):  
        """Clone the item in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        folder - The folder to create the item in"""
    
        try:
            new_item = None
            original_item = self.info
        
            # Get the item properties from the original item to be applied when the new item is created
            item_properties = self._get_item_properties()
            if extent:
                item_properties['extent'] = extent['wgs84']

            with tempfile.TemporaryDirectory() as temp_dir:
                data = self.data
                if not data and self.portal_item:
                    data = self.portal_item.download(temp_dir)
                
                # The item's name will default to the name of the data, if it already exists in the folder we need to rename it to something unique
                name = os.path.basename(data)
                item = next((item for item in target.users.me.items(folder['title']) if item['name'] == name), None)
                if item:
                    new_name = "{0}_{1}{2}".format(os.path.splitext(name)[0], str(uuid.uuid4()).replace('-',''), os.path.splitext(name)[1])
                    new_path = os.path.join(temp_dir, new_name)
                    os.rename(data, new_path)
                    data = new_path

                # Add the new item
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

class TextItemDefinition(ItemDefinition):
    """
    Represents the definition of a text based item within ArcGIS Online or Portal.
    """

    def _update_feature_attributes_for_portal(self, feature):
        if 'attributes' in feature and feature['attributes'] is not None:
            for attribute in [att for att in feature['attributes']]:
                att_lower = attribute.lower()
                if att_lower in feature['attributes']:
                    continue
                feature['attributes'][att_lower] = feature['attributes'][attribute]
                del feature['attributes'][attribute]

    def _update_fields_for_portal(self, layer):
        if 'templates' in layer and layer['templates'] is not None:
            for template in layer['templates']:
                if 'prototype' in template and template['prototype'] is not None:
                    self._update_feature_attributes_for_portal(template['prototype'])
                    
        if 'drawingInfo' in layer and layer['drawingInfo'] is not None:
            if 'renderer' in layer['drawingInfo'] and layer['drawingInfo']['renderer'] is not None:
                renderer = layer['drawingInfo']['renderer']
                if renderer['type'] == 'uniqueValue':
                    i = 0
                    while 'field{0}'.format(i) in renderer:
                        renderer['field{0}'.format(i)] = renderer['field{0}'.format(i)].lower()
                        i += 1
                elif renderer['type'] == 'classBreaks':
                    if 'field' in renderer:
                        renderer['field'] = renderer['field'].lower()
                        
            if 'labelingInfo' in layer['drawingInfo'] and layer['drawingInfo']['labelingInfo'] is not None:
                labeling_infos = layer['drawingInfo']['labelingInfo']
                for label_info in labeling_infos:
                    if 'labelExpression' in label_info:
                        results = re.findall(r"\[.*\]", label_info['labelExpression'])
                        for result in results:
                            label_info['labelExpression'] = str(label_info['labelExpression']).replace(result,str(result).lower())

                    if 'labelExpressionInfo' in label_info and 'value' in label_info['labelExpressionInfo']:
                        results = re.findall(r"{.*}", label_info['labelExpressionInfo']['value'])
                        for result in results:
                            label_info['labelExpressionInfo']['value'] = str(label_info['labelExpressionInfo']['value']).replace(result,str(result).lower())
    
        if 'popupInfo' in layer and layer['popupInfo'] is not None:
            if 'title' in layer['popupInfo'] and layer['popupInfo']['title'] is not None:
                results = re.findall(r"\{.*\}", layer['popupInfo']['title'])
                for result in results:
                    layer['popupInfo']['title'] = str(layer['popupInfo']['title']).replace(result,str(result).lower())
                
            if 'description' in layer['popupInfo'] and layer['popupInfo']['description'] is not None:
                results = re.findall(r"\{.*\}", layer['popupInfo']['description'])
                for result in results:
                    layer['popupInfo']['description'] = str(layer['popupInfo']['description']).replace(result,str(result).lower())

            if 'fieldInfos' in layer['popupInfo'] and layer['popupInfo']['fieldInfos'] is not None:
                for field in layer['popupInfo']['fieldInfos']:
                    field['fieldName'] = field['fieldName'].lower()

            if 'mediaInfos' in layer['popupInfo'] and layer['popupInfo']['mediaInfos'] is not None:
                for media_info in layer['popupInfo']['mediaInfos']:
                    if 'title' in media_info and media_info['title'] is not None:
                        results = re.findall(r"\{.*\}", media_info['title'])
                        for result in results:
                            media_info['title'] = str(media_info['title']).replace(result,str(result).lower())
                    if 'caption' in media_info and media_info['caption'] is not None:
                        results = re.findall(r"\{.*\}", media_info['caption'])
                        for result in results:
                            media_info['caption'] = str(media_info['caption']).replace(result,str(result).lower())
                    if 'normalizeField' in media_info and media_info['normalizeField'] is not None:
                        media_info['normalizeField'] = media_info['normalizeField'].lower()
                    if 'fields' in media_info and media_info['fields'] is not None:
                        media_info['fields'] = [field.lower() for field in media_info['fields']]

    def clone(self, target, extent=None, group_mapping={}, folder=None):  
        """Clone the item in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        folder - The folder to create the item in"""
    
        try:
            new_item = None
            original_item = self.info
        
            # Get the item properties from the original item to be applied when the new item is created
            item_properties = self._get_item_properties()
            if extent:
                item_properties['extent'] = extent['wgs84']
            data = self.data
            if data:
                item_properties['text'] = json.dumps(data)
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
        item_directory = ItemDefinition.write(self, items_directory)
        if not item_directory:
            return None

        item_id = self.info['id']
        data_json = os.path.join(item_directory, item_id + '.json')
        with open(data_json, 'w') as file:
            file.write(json.dumps(self._data))

        return item_directory

class FeatureServiceDefinition(TextItemDefinition):
    """
    Represents the definition of a hosted feature service within ArcGIS Online or Portal.
    """

    def __init__(self, info, service_definition, layers_definition, features=None, data=None, sharing=None, thumbnail=None, portal_item=None):
        self._service_definition = service_definition
        self._layers_definition = layers_definition
        self._features = features
        super(TextItemDefinition, self).__init__(info, data, sharing, thumbnail, portal_item)

    @property
    def service_definition(self):
        return copy.deepcopy(self._service_definition)

    @property
    def layers_definition(self):
        return copy.deepcopy(self._layers_definition)

    @property
    def features(self):
        return copy.deepcopy(self._features)

    def _add_features(self, target, layers, relationships):
        """Add the features from the definition to the layers returned from the cloned item.
        Keyword arguments:
        layers - Dictionary containing the id of the layer and its corresponding arcgis.lyr.FeatureLayer
        relationships - Dictionary containing the id of the layer and it's relationship definitions"""

        features = self.features   
        if features:
            # If writing to Portal we need to change the case of the feature attribute field names
            if target.properties.isPortal:
                for id in features:
                    for feature in features[id]:
                        self._update_feature_attributes_for_portal(feature)

            # Add in chunks of 2000 features
            chunk_size = 2000
            layer_ids = [id for id in layers]

            # Find all the relates where the layer's role is the origin and the key field is the global id field
            # We want to process these first, get the new global ids that are created and update in related features before processing the relates
            for id in relationships:                  
                if id not in layer_ids or id not in layers:
                    continue

                admin_properties = layers[id].admin.properties  
                if 'globalIdField' not in admin_properties:  
                    continue

                global_id_field = admin_properties['globalIdField']
                relates = [relate for relate in relationships[id] if relate['role'] == 'esriRelRoleOrigin' and relate['keyField'] == global_id_field]
                if len(relates) == 0:
                    continue

                layer = layers[id]
                layer_features = features[str(id)]
                if len(layer_features) == 0:
                    layer_ids.remove(id)
                    continue

                # Add the features to the layer in chunks
                add_results = []
                for features_chunk in [layer_features[i:i+chunk_size] for i in range(0, len(layer_features), chunk_size)]:
                    edits = layer.edit_features(adds=features_chunk)
                    add_results += edits['addResults']
                layer_ids.remove(id)

                # Create a mapping between the original global id and the new global id
                global_id_mapping = { layer_features[i]['attributes'][global_id_field] : add_results[i]['globalId'] for i in range(0, len(layer_features)) }

                for relate in relates:
                    related_layer_id = relate['relatedTableId']
                    if related_layer_id not in layer_ids:
                        continue
                    related_layer_features = features[str(related_layer_id)]
                    if len(related_layer_features) == 0:
                        layer_ids.remove(related_layer_id)
                        continue

                    # Get the definition of the definition relationship
                    destination_relate = next((r for r in relationships[related_layer_id] if r['id'] == relate['id'] and r['role'] == 'esriRelRoleDestination'), None)
                    if not destination_relate:
                        continue

                    key_field = destination_relate['keyField']

                    # Update the relate features keyfield to the new global id
                    for feature in related_layer_features:
                        if key_field in feature['attributes']:
                            global_id = feature['attributes'][key_field]
                            if global_id in global_id_mapping:
                                feature['attributes'][key_field] = global_id_mapping[global_id]

                    # Add the related features to the layer in chunks
                    for features_chunk in [related_layer_features[i:i+chunk_size] for i in range(0, len(layer_features), chunk_size)]:
                        layers[related_layer_id].edit_features(adds=features_chunk)
                    layer_ids.remove(related_layer_id)
                      
            # Add features to all other layers and tables                           
            for id in layer_ids:
                layer_features = features[str(id)]
                if len(layer_features) == 0:
                    continue
                for features_chunk in [layer_features[i:i+chunk_size] for i in range(0, len(layer_features), chunk_size)]:
                    layers[id].edit_features(adds=features_chunk)

    def clone(self, target, extent, group_mapping={}, folder=None):
        """Clone the feature service in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        extent - Default extent of the new feature service in WGS84
        folder - The folder to create the service in"""

        try:
            new_item = None
            original_item = self.info

            # Get the definition of the original feature service
            service_definition = self.service_definition

            # Modify the definition before passing to create the new service
            name = original_item['name']
            if not target.content.is_service_name_available(name, 'featureService'):
                name = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))       
            service_definition['name'] = name
    
            for key in ['layers', 'tables']:
                if key in service_definition:
                    del service_definition[key]
            service_definition['initialExtent'] = extent['web_mercator']
            service_definition['spatialReference'] = { "spatialReference" : {
		                                    "wkid" : 102100, "latestWkid" : 3857}}

            # Create a new feature service
            new_item = target.content.create_service(name, service_type='featureService', create_params=service_definition, folder=folder['title'])

            # Get the layer and table definitions from the original service and prepare them for the new service
            layers_definition = self.layers_definition
            relationships = {} 
            for layer in layers_definition['layers'] + layers_definition['tables']:
                # Need to remove relationships first and add them back individually 
                # after all layers and tables have been added to the definition
                if 'relationships' in layer and layer['relationships'] is not None and len(layer['relationships']) != 0:
                    if target.properties.isPortal:
                        for relationship in layer['relationships']:
                            relationship['keyField'] = relationship['keyField'].lower()
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
                if layer['type'] == 'Feature Layer':
                    layer['extent'] = extent['web_mercator']

                if target.properties.isPortal:
                    self._update_fields_for_portal(layer)
        
            # Add the layer and table definitions to the service
            # Explicitly add layers first and then tables, otherwise sometimes json.dumps() reverses them and this effects the output service
            feature_service = lyr.FeatureService.fromitem(new_item)
            feature_service_admin = feature_service.admin
            if len(layers_definition['layers']) > 0:
                feature_service_admin.add_to_definition({'layers' : layers_definition['layers']})
            if len(layers_definition['tables']) > 0:
                feature_service_admin.add_to_definition({'tables' : layers_definition['tables']})
            
            # Create a lookup for the layers and tables using their id
            layers = { layer.properties['id'] : layer for layer in feature_service.layers + feature_service.tables }
                
            # Add the relationships back to the layers
            if len(relationships) > 0:
                if target.properties.isPortal:
                    relationships_definition = {'layers' : []}
                    for id in relationships:
                        relationships_definition['layers'].append({ 'id' : id, 'relationships' : relationships[id] })                
                    feature_service_admin.add_to_definition(relationships_definition)  
                else:
                    for id in relationships:
                        layer = layers[id]
                        layer.admin.add_to_definition({'relationships' : relationships[id]})

            # Update the item definition of the service
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']
            data = self.data
            if data:
                if target.properties.isPortal:
                    if 'layers' in data and data['layers'] is not None:
                        for layer in data['layers']:
                            self._update_fields_for_portal(layer)
                item_properties['text'] = json.dumps(data)
            new_item.update(item_properties=item_properties, thumbnail=self.thumbnail)
    
            # Copy features from original item
            self._add_features(target, layers, relationships)

            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

    def write(self, items_directory):
        """Write the definition of the feature service to a local directory.
        Keyword arguments:
        items_directory - The items directory containing the definitions of the groups and items"""
        item_directory = TextItemDefinition.write(self, items_directory)
        if not item_directory:
            return None
        esriinfo_directory = os.path.join(item_directory, 'esriinfo')

        featureserver_json = os.path.join(esriinfo_directory, "featureserver.json")
        with open(featureserver_json, 'w') as file:
            file.write(json.dumps({'serviceDefinition' : self._service_definition, 'layersDefinition' : self._layers_definition}))

        features = self.features
        if features:
            features_json = os.path.join(esriinfo_directory, "features.json")
            with open(features_json, 'w') as file:
                file.write(json.dumps(features))  

        return item_directory

class WebMapDefinition(TextItemDefinition):
    """
    Represents the definition of a web map within ArcGIS Online or Portal.
    """

    def clone(self, target, extent, group_mapping={}, service_mapping={}, folder=None):  
        """Clone the web map in the target organization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        service_mapping - Dictionary containing the mapping between the original service url and new service item id and url
        extent - Default extent of the new web map in WGS84
        folder - The folder to create the web map in"""
    
        try:
            new_item = None
            original_item = self.info
        
            # Get the item properties from the original web map which will be applied when the new item is created
            item_properties = self._get_item_properties()
            item_properties['extent'] = extent['wgs84']

            # Swizzle the item ids and URLs of the feature layers and tables in the web map
            webmap_json = self.data

            layers = []
            if 'operationalLayers' in webmap_json:
                layers += [layer for layer in webmap_json['operationalLayers'] if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer" and 'url' in layer]
            if 'tables' in webmap_json:
                layers += [table for table in webmap_json['tables'] if 'url' in table]

            for layer in layers:
                feature_service_url = os.path.dirname(layer['url'])
                for original_url in service_mapping:
                    if feature_service_url.lower() == original_url.lower(): 
                        layer_id = os.path.basename(layer['url'])
                        layer['url'] = "{0}/{1}".format(service_mapping[original_url]['url'], layer_id)
                        layer['itemId'] = service_mapping[original_url]['id']
                        if target.properties.isPortal:
                            self._update_fields_for_portal(layer)
                        break

            # Add the web map to the target portal
            item_properties['text'] = json.dumps(webmap_json)
            new_item = target.content.add(item_properties=item_properties, thumbnail=self.thumbnail, folder=folder['title'])

            # Share the item
            self._share_new_item(new_item, group_mapping)

            return new_item
        except Exception as e:
            raise ItemCreateException("Failed to create {0} {1}: {2}".format(original_item['type'], original_item['title'], str(e)), new_item)

class ApplicationDefinition(TextItemDefinition):
    """
    Represents the definition of an application within ArcGIS Online or Portal.
    """
    
    def clone(self, target, group_mapping={}, service_mapping={}, webmap_mapping={}, folder=None):
        """Clone the application in the target orgnaization.
        Keyword arguments:
        connection - Dictionary containing connection info to the target portal
        group_mapping - Dictionary containing the id of the original group and the id of the new group
        service_mapping - Dictionary containing the mapping between the original service url and new service item id and url
        webmap_mapping - Dictionary containing a mapping between the original web map id and new web map id
        folder - The folder to create the application in"""  
    
        try:
            new_item = None
            original_item = self.info
            portal_url = target._portal.url

            # Get the item properties from the original application which will be applied when the new item is created
            item_properties = self._get_item_properties()

            # Swizzle the item ids of the web maps, groups and URLs of defined in the application's data
            app_json = self.data
            if "Web AppBuilder" in original_item['typeKeywords']: #Web AppBuilder
                if 'portalUrl' in app_json:
                    app_json['portalUrl'] = portal_url
                if 'map' in app_json:
                    if 'portalUrl' in app_json['map']:
                        app_json['map']['portalUrl'] = portal_url
                    if 'itemId' in app_json['map']:
                        app_json['map']['itemId'] = webmap_mapping[app_json['map']['itemId']]
                if 'httpProxy' in app_json:
                    if 'url' in app_json['httpProxy']:
                        app_json['httpProxy']['url'] = portal_url + "sharing/proxy"
        
                app_json_text = json.dumps(app_json)        
                for service_url in service_mapping:
                    url_pattern = re.compile(service_url, re.IGNORECASE)
                    app_json_text = url_pattern.sub(service_mapping[service_url]['url'], app_json_text)
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
                new_url = '{0}{1}'.format(portal_url.rstrip('/'), original_item['url'][index:])
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

#endregion

#region Public API Functions

def download_items(item_definitions, output_directory):
    """Download items from a portal to a local directory
    Keyword arguments:
    item_definitions - A list of item and group definitions to be downloaded. This list can be created from an existing item by calling get_item_defintions_recursive.
    output_directory - The directory to write the items"""  

    # Write the items to the output directory
    for item in [item for item in item_definitions if isinstance(item, ItemDefinition)]:
        item_directory = item.write(output_directory)
        if item_directory:
            _add_message("Downloaded {0} {1}".format(item.info['type'], item.info['title']))
        else:
            _add_message("Existing {0} {1} already downloaded".format(item.info['type'], item.info['title']))

    # Write the groups to the output directory
    for group in [group for group in item_definitions if isinstance(group, GroupDefinition)]:
        group_directory = group.write(output_directory)
        if group_directory:
            _add_message("Downloaded Group {0}".format(group.info['title']))
        else:
            _add_message("Existing Group {0} already downloaded".format(group.info['title']))
      
    return True 

def clone_item(target, item, folder_name, extent=None, copy_data=False):
    """Clone an item to a portal. If a web map or application is passed in, all services and groups that support the application will also be cloned.
    Keyword arguments:
    target - The instance of arcgis.gis.GIS (the portal) to clone the items to.
    item - The arcgis.GIS.Item to clone.
    folder_name - The name of the folder to clone the new items to. If the folder does not already exist it will be created.
    extent - An arcpy.Extent used to specify the default extent of the new cloned items. If None the default extent defined in the target portal will be used.
    copy_data- A flag indicating if the data from the original feature services should be copied to the cloned service"""  

    group_mapping = {}   
    service_mapping = {}
    webmap_mapping = {}
    created_items = []

    try:
        # Check if the item has already been cloned into the target portal  
        folder_items = []
        folders = target.users.me.folders
        folder = next((folder for folder in folders if folder['title'] == folder_name), None)
        if folder:
            folder_items = target.users.me.items(folder_name)
            existing_item = _get_existing_item(item, folder_items)
            if existing_item:
                _add_message("{0} already exists in {1} folder".format(item['title'], folder_name))
                _add_message('------------------------')
                return
        #If the folder does not already exist create a new folder
        else:
            folder = target.content.create_folder(folder_name)

        # Get the definitions associated with the item
        item_definitions = []
        _get_item_definitions(item, item_definitions, copy_data)

        # Get the extent definition
        default_extent = _get_extent_definition(target, extent)

        #If the folder does not already exist create a new folder
        current_user = target.users.me
        folders = current_user.folders
        folder = next((folder for folder in folders if folder['title'] == folder_name), None)
        if not folder:
            folder = target.content.create_folder(folder_name)

        # Clone the groups
        for group in [group for group in item_definitions if isinstance(group, GroupDefinition)]:
            item_definitions.remove(group)
            original_group = group.info
                
            new_group = _get_existing_group(target, original_group, folder)
            if not new_group:
                new_group = group.clone(target, folder)
                created_items.append(new_group)
                _add_message("Created Group {0}".format(new_group['title']))
            else:
                _add_message("Existing Group {0} found".format(new_group['title']))
            group_mapping[original_group['id']] = new_group['id']

        # Clone the feature services
        for feature_service in [item for item in item_definitions if isinstance(item, FeatureServiceDefinition)]:
            item_definitions.remove(feature_service)
            original_item = feature_service.info

            new_item = _get_existing_item(original_item, folder_items)
            if not new_item:                     
                new_item = feature_service.clone(target, default_extent, group_mapping, folder)
                created_items.append(new_item)
                _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
            else:
                _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))        
            service_mapping[original_item['url']] = { 'id' : new_item['id'], 'url' : new_item['url'] }

        # Clone the web maps
        for webmap in [item for item in item_definitions if isinstance(item, WebMapDefinition)]:
            item_definitions.remove(webmap)
            original_item = webmap.info

            if original_item['id'] in webmap_mapping: #We have already found or created this item
                _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))   
                continue
          
            new_item = _get_existing_item(original_item, folder_items)
            if not new_item:
                new_item = webmap.clone(target, default_extent, group_mapping, service_mapping, folder)
                created_items.append(new_item)
                _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
            else:
                _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))   
            webmap_mapping[original_item['id']] =  new_item['id']

        # Clone the applications
        for application in [item for item in item_definitions if isinstance(item, ApplicationDefinition)]:
            item_definitions.remove(application)
            original_item = application.info

            new_item = _get_existing_item(original_item, folder_items)
            if not new_item:                   
                new_item = application.clone(target, group_mapping, service_mapping, webmap_mapping, folder)
                created_items.append(new_item)
                _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
            else:
                _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title'])) 
            
        # Clone all other items
        for item in item_definitions:
            original_item = item.info

            new_item = _get_existing_item(original_item, folder_items)
            if not new_item:                   
                new_item = item.clone(target, default_extent, group_mapping, folder)
                created_items.append(new_item)
                _add_message("Created {0} {1}".format(new_item['type'], new_item['title']))   
            else:
                _add_message("Existing {0} {1} found in {2} folder".format(original_item['type'], original_item['title'], folder['title']))            

        _add_message('Successfully added {0}'.format(item['title']))
        _add_message('------------------------')

    except Exception as e:
        if type(e) == ItemCreateException:
            _add_message(e.args[0], 'Error')
            if e.args[1] is not None:
                created_items.append(e.args[1])
        else:
            _add_message(str(e), 'Error')

        for solution_item in created_items:
            if solution_item.delete():
                _add_message("Deleted {0}".format(solution_item['title']))
                
        _add_message('Failed to add {0}'.format(item['title']), 'Error')
        _add_message('------------------------')

#endregion

#region Private API Functions

def _get_item_definitions(item, item_definitions, copy_data=False):
    """" Get a list of definitions for the specified item. 
    This method differs from get_item_defintion in that it is run recursively to return the definitions of feature service items that make up a webmap and the groups and webmaps that make up an application.
    These definitions can be used to clone or download the items.
    Keyword arguments:
    item - The arcgis.GIS.Item to get the definition for
    item_definitions - A list of item and group definitions. When first called this should be an empty list that you hold a reference to and all definitions related to the item will be appended to the list.
    copy_data- A flag indicating if the data from the original feature services should be added to the definition to be cloned or downloaded"""  

    item_definition = None
    source = item._gis

    # Check if the item definition has already been added to the definition of the solution
    item_definition = next((i for i in item_definitions if i.info['id'] == item.id), None)
    if item_definition:
        return item_definition

    # if the item is a group find all the web maps that are shared with the group
    if isinstance(item, gis.Group):
        item_definition = _get_group_definition(item)
        item_definitions.append(item_definition)
                    
        search_query = 'group:{0} AND type:{1}'.format(item['id'], 'Web Map')
        group_items = source.content.search(search_query, max_items=100, outside_org=True)
        for webmap in group_items:
            webmap_definition = _get_item_definitions(webmap, item_definitions, copy_data)
            webmap_definition.sharing['groups'] = [item['id']]

    # If the item is an application or dashboard find the web map or group that the application referencing
    elif item['type'] in ['Web Mapping Application','Operation View']:
        item_definition = _get_item_defintion(item)
        item_definitions.append(item_definition)
   
        app_json = item_definition.data
        webmap_id = None
        if item['type'].lower() == "operation view": #Operations Dashboard
            if 'widgets' in app_json:
                for widget in app_json['widgets']:
                    if 'mapId' in widget:
                        webmap_id = widget['mapId']
                        break

        elif "Web AppBuilder" in item['typeKeywords']: #Web AppBuilder
            if 'map' in app_json:
                if 'itemId' in app_json['map']:
                    webmap_id = app_json['map']['itemId']

        else: #Configurable Application Template
            if 'values' in app_json:
                if 'group' in app_json['values']:
                    group_id = app_json['values']['group']
                    try:
                        group = source.groups.get(group_id)
                    except RuntimeError:
                        _add_message("Failed to get group {0}".format(group_id, 'Error'))
                        raise
                    _get_item_definitions(group, item_definitions, copy_data)

                if 'webmap' in app_json['values']:
                    webmap_id = app_json['values']['webmap']
        
        if webmap_id:
            try:
                webmap = source.content.get(webmap_id)
            except RuntimeError:
                _add_message("Failed to get web map {0}".format(webmap_id, 'Error'))
                raise
            _get_item_definitions(webmap, item_definitions, copy_data)

    # If the item is a web map find all the feature service layers and tables that make up the map
    elif item['type'] == 'Web Map':
        item_definition = _get_item_defintion(item)
        item_definitions.append(item_definition)
        
        webmap_json = item_definition.data
        layers = []

        if 'operationalLayers' in webmap_json:
            layers += [layer for layer in webmap_json['operationalLayers'] if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer" and 'url' in layer]
        if 'tables' in webmap_json:
            layers += [table for table in webmap_json['tables'] if 'url' in table]

        for layer in layers:
            feature_service_url = os.path.dirname(layer['url'])
            feature_service = next((definition for definition in item_definitions if 'url' in definition.info and definition.info['url'] == feature_service_url), None)
            if not feature_service:
                try:
                    service = lyr.FeatureService(feature_service_url, source)
                except RuntimeError:
                    _add_message("Failed to get service {0}".format(feature_service_url, 'Warning'))
                    continue

                if 'serviceItemId' not in service.properties:
                    continue

                try:
                    item_id = service.properties['serviceItemId']
                    feature_service = source.content.get(item_id)
                except RuntimeError:
                    _add_message("Failed to get service item {0}".format(item_id, 'Error'))
                    raise
                _get_item_definitions(feature_service, item_definitions, copy_data)

    # All other types we no longer need to recursively look for related items
    else:
        item_definition = _get_item_defintion(item, copy_data)
        item_definitions.append(item_definition)

    return item_definition

def _get_item_definitions_local(items_directory, solution_name, item_definitions, cached_definitions=None, copy_data=False):
    """Get the definition of items for a given solution from a local representation of the items. This may be made up of multiple items and groups.
    Keyword arguments:
    items_directory - The directory containing the items and the SolutionDefinition.json file that defines the items that make up a given solution.
    solution_name - The name of the solution to get the definitions for.
    item_definitions - A list of item and group definitions. When first called this should be an empty list that you hold a reference to and all definitions related to the item will be appended to the list.
    cached_defintions -  Optionally pass in a list of definitions that have been previously returned for items. This reduces the need to re-query the items for their definitions
    copy_data- A flag indicating if the data from the original feature services should be added to the definition to be cloned or downloaded""" 

    # Read the SolutionDefinitions.json file to get the IDs of the items and groups that make up the solution
    solutions_definition_file = os.path.join(items_directory, 'SolutionDefinitions.json') 
    definitions = None
    if os.path.exists(solutions_definition_file):
        with open(solutions_definition_file, 'r') as file:
            content = file.read() 
            definitions = json.loads(content)
    
    if not definitions:
        raise Exception("Source directory does not contain a valid SolutionDefinitions configuration file")

    if solution_name not in definitions['Solutions']:
        raise Exception("The SolutionDefinitions configuration file does not contain a definition for {0}".format(solution_name))

    # Get the definition of each item defined within the solution
    for item_id in definitions['Solutions'][solution_name]['items']:
        if cached_definitions:
            cached_item = next((i for i in cached_definitions if i.info['id'] == item_id), None)
            if cached_item:
                item_definitions.append(cached_item)
                continue

        item_directory = os.path.join(items_directory, item_id)
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
                if copy_data:
                    features_file = os.path.join(esriinfo_directory, 'features.json')
                    if os.path.exists(features_file):
                        with open(features_file, 'r') as file:
                            features_json = json.loads(file.read())

                solution_item = FeatureServiceDefinition(item['info'], featureserver_json['serviceDefinition'], featureserver_json['layersDefinition'], features=features_json, data=data, sharing=item['sharing'])

            elif type == 'Web Map':
                solution_item = WebMapDefinition(item['info'], data, item['sharing'])
            elif type in ['Web Mapping Application', 'Operation View']:
                solution_item = ApplicationDefinition(item['info'], data, item['sharing'])
            else:
                solution_item = TextItemDefinition(item['info'], data, item['sharing'])
        else:
            solution_item = ItemDefinition(item['info'], data, item['sharing'])

        # If the item has a thumbnail find the path
        thumbnail_directory = os.path.join(esriinfo_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_item.thumbnail = thumbnail

        # Append the item to the list
        item_definitions.append(solution_item)

    # Get the definition of each group defined within the solution
    for group_id in definitions['Solutions'][solution_name]['groups']:
        cached_item = next((i for i in cached_definitions if i.info['id'] == group_id), None)
        if cached_item:
            item_definitions.append(cached_item)
            continue

        group_directory = os.path.join(items_directory, 'groupinfo', group_id)
        if not os.path.exists(group_directory):
            raise Exception("Group: {0} was not found of the groupinfo under the source directory".format(group_id))

        # Find and read the groupinfo file which describe the group
        solution_group = None
        groupinfo = os.path.join(group_directory, 'groupinfo.json')
        with open(groupinfo, 'r') as file:
            content = file.read() 
            group = json.loads(content)
            solution_group = GroupDefinition(group)

        # If the group has a thumbnail find the path
        thumbnail_directory = os.path.join(group_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_group.thumbnail = thumbnail

        # Append the group to the list
        item_definitions.append(solution_group)

def _get_group_definition(group):
    """Get an instance of the group definition for the specified item. This definition can be used to clone or download the group.
    Keyword arguments:
    group - The arcgis.GIS.Group to get the definition for.""" 
    return GroupDefinition(dict(group), thumbnail=group.get_thumbnail_link(), portal_group=group)

def _get_item_defintion(item, copy_data=False):
    """Get an instance of the corresponding definition class for the specified item. This definition can be used to clone or download the item.
    Keyword arguments:
    item - The arcgis.GIS.Item to get the definition for.
    copy_data - A flag indicating if in the case of a feature service if the data from the original feature should be added to the definition to be cloned or downloaded."""  
       
    # If the item is an application or dashboard get the ApplicationDefinition
    if item['type'] in ['Web Mapping Application','Operation View']:
        app_json = item.get_data()
        return ApplicationDefinition(dict(item), data=app_json, thumbnail=item.get_thumbnail_link(), portal_item=item)
      
    # If the item is a web map get the WebMapDefintion
    elif item['type'] == 'Web Map':
        webmap_json = item.get_data()
        return WebMapDefinition(dict(item), data=webmap_json, thumbnail=item.get_thumbnail_link(), portal_item=item)

    # If the item is a feature service get the FeatureServiceDefintion
    elif item['type'] == 'Feature Service':
        svc = lyr.FeatureService.fromitem(item)
        service_definition = dict(svc.properties)

        # Get the definitions of the the layers and tables
        layers_definition = { 'layers' : [], 'tables' : [] }
        for layer in svc.layers:
            layers_definition['layers'].append(dict(layer.properties))
        for table in svc.tables:
            layers_definition['tables'].append(dict(table.properties))
        
        # Get the item data, for example any popup definition associated with the item
        data = item.get_data()     
        
        # Get the features for the layers and tables if requested
        features = None
        if copy_data:
            features = {}
            for layer in svc.layers + svc.tables:
                features[str(layer.properties['id'])] = _get_features(layer)

        return FeatureServiceDefinition(dict(item), service_definition, layers_definition, features=features, data=data, thumbnail=item.get_thumbnail_link(), portal_item=item)

    # For all other types get the corresponding definition
    else:
        if item['type'] in TEXT_BASED_ITEM_TYPES:
            return TextItemDefinition(dict(item), data=item.get_data(), thumbnail=item.get_thumbnail_link(), portal_item=item)
        else:
            return ItemDefinition(dict(item), data=None, thumbnail=item.get_thumbnail_link(), portal_item=item)

def _add_message(message, type='Info'):
    """Add a message to the output"""
    if type == 'Info':
        arcpy.AddMessage(message)
    elif type == 'Warning':
        arcpy.AddWarning(message)
    elif type == 'Error':
        arcpy.AddError(message)

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
        features = feature_layer.query(as_dict=True, outSR=102100, resultOffset=offset, resultRecordCount=max_record_count)['features']
        offset += len(features)
        total_features += features
    return total_features

def _get_extent_definition(target, extent=None):
    """Get a dictionary representation of an arcpy.Extent object that is used by the clone_items method. 
    This creates a WGS84 and Web Mercator representation of the extent that is used when setting the spatial reference of feature services and the default extent of items. 
    Keyword arguments:
    target - The portal that items will be cloned to.
    extent - Optionally provide an arcpy.Extent to be used. If no extent is provided it will return the default extent defined in the target portal."""   
    
    coordinates = []
    sr = None

    if extent:
        default_extent = {'xmin' : extent.XMin, 'xmax' : extent.XMax, 'ymin' : extent.YMin, 'ymax' : extent.YMax }
        sr = extent.spatialReference
    else: # Get the default extent defined in the portal
        default_extent = target.properties['defaultExtent']
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

def _get_existing_item(item, folder_items):
    """Test if an item with a given source tag already exists in the collection of items within a given folder. 
    This is used to determine if the item has already been cloned in the folder.
    Keyword arguments:
    item - The original item used to determine if it has already been cloned to the specified folder.
    folder_items - A list of items from a given folder used to search if the item has already been cloned."""  
   
    return next((folder_item for folder_item in folder_items if folder_item['type'] == item['type'] 
                          and "source-{0}".format(item['id']) in folder_item['typeKeywords']), None)

def _get_existing_group(target, group, linked_folder):
    """Test if a group with a given source tag already exists in the organization. 
    This is used to determine if the group has already been created and if new maps and apps that belong to the same group should be shared to the same group.
    Keyword arguments:
    group - The original group used to determine if it has already been cloned in the organization.
    linked_folder - The folder in which new items are created. Each group is tied to a given folder and when applicable the items in that folder are shared with the associated group.""" 
    
    search_query = 'tags:"source-{0},sourcefolder-{1}"'.format(group['id'], linked_folder['id']) 
    groups = target.groups.search(search_query)
    if len(groups) > 0:
        return groups[0]
    return None

def _get_fields(parameter):
    feature_layer = _get_feature_layer(parameter)

    if feature_layer in ["Invalid URL", "Failed To Connect"]:
        return feature_layer

    return json.dumps(feature_layer.properties['fields'])

def _get_feature_layer(parameter):
    url = None
    desc = arcpy.Describe(parameter.value)
    url = desc.path

    if not url.endswith('/FeatureServer'):
        return "Invalid URL"

    if url.startswith('GIS Servers\\'):
        url = 'https://{0}'.format(url[len('GIS Servers\\'):])

    try:
        layer_id = int(desc.name)
    except:
        name = desc.name[1:]
        layer_id = ''
        for c in name:
            if c in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                layer_id += c
            else:
                break
        layer_id = int(layer_id)

    try:
        feature_service = lyr.FeatureService(url, gis.GIS('pro'))
        feature_layer = next((layer for layer in feature_service.layers + feature_service.tables if layer.properties['id'] == layer_id), None)
        if not feature_layer or 'serviceItemId' not in feature_service.properties:
            return "Invalid URL"
        
        return feature_layer
    except:
        return "Failed To Connect"

#endregion