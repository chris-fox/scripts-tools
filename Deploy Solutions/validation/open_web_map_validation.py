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
import arcpy
from arcgis import gis
from scripts import _solution_helpers

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
        if not self.params[3].value:
            target = gis.GIS('pro')          
            current_user = target.users.me
            content = current_user.content()
            for key in content:
                content[key] = [item for item in content[key] if item.type == 'Web Map']
            content[current_user.username] = content['/']
            del content['/']
            self.params[0].filter.list= sorted(content.keys())
            _solution_helpers.set_validation_json(content)
            self.params[3].value = True

        if not self.params[0].hasBeenValidated and self.params[0].value is not None:
            content = _solution_helpers.get_validation_json()
            folder = self.params[0].valueAsText
            self.params[1].filter.list = sorted([item.title for item in content[folder]])

        if not self.params[1].hasBeenValidated and self.params[1].value is not None and self.params[0].value is not None:
            content = _solution_helpers.get_validation_json()
            folder = self.params[0].valueAsText
            webmap = next((item for item in content[folder] if item.title == self.params[1].valueAsText), None)
            self.params[2].value = webmap.id
        return
    
    def updateMessages(self):
        """Modify the messages created by internal validation for each tool"""
        return

