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
            folders = current_user.folders  
            username = current_user.username     
            validation_dict = { 'portal' : target, 'username' : username }
            _solution_helpers.set_validation_dict(validation_dict)
            folders = sorted([folder['title'] for folder in folders])
            folders.insert(0, username)
            self.params[0].filter.list = folders
            self.params[3].value = True

        if not self.params[0].hasBeenValidated and self.params[0].value is not None:
            validation_dict = _solution_helpers.get_validation_dict()
            target = validation_dict['portal']
            folder = self.params[0].valueAsText
            if folder == validation_dict['username']:
                folder = None
            items = [item for item in target.users.me.items(folder) if item.type.lower() == "web map"] 
            validation_dict['items'] = items
            _solution_helpers.set_validation_dict(validation_dict)
            self.params[1].value = None
            self.params[1].filter.list = sorted([item.title for item in items])          

        if not self.params[1].hasBeenValidated and self.params[1].value is not None and self.params[0].value is not None:
            items = _solution_helpers.get_validation_dict()['items']
            webmap = next((item for item in items if item.title == self.params[1].valueAsText), None)
            if webmap is None:
                return
            url = "{0}home/webmap/viewer.html?webmap={1}".format(arcpy.GetActivePortalURL(), webmap.id)
            self.params[2].value = url
        return
    
    def updateMessages(self):
        """Modify the messages created by internal validation for each tool"""
        return

