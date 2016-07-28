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
import json, arcpy, os
from scripts import _solution_helpers
from arcgis import gis

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
        if not self.params[1].hasBeenValidated and self.params[1].value:
            solutions_definition_file = os.path.join(self.params[1].valueAsText, 'SolutionDefinitions.json') 
            if os.path.exists(solutions_definition_file):
                with open(solutions_definition_file, 'r') as file:
                    content = file.read() 
                    definitions = json.loads(content)
                    self.params[2].filter.list = sorted([solution_name for solution_name in definitions['Solutions']])

            target = gis.GIS('pro')
            folders = target.users.me.folders
            self.params[5].filter.list = sorted([folder['title'] for folder in folders])
        
        if not self.params[2].hasBeenValidated and self.params[2].value:
            solutions_definition_file = os.path.join(self.params[1].valueAsText, 'SolutionDefinitions.json') 
            if os.path.exists(solutions_definition_file):
                solution_name = self.params[2].valueAsText
                with open(solutions_definition_file, 'r') as file:
                    content = file.read() 
                    definitions = json.loads(content)
                    if solution_name in definitions['Solutions']:
                        self.params[3].filter.list = sorted(definitions['Solutions'][solution_name])
    
    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        self.params[5].clearMessage()
