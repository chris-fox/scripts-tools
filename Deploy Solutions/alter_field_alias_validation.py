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
import json, arcpy
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

    def updateParameters(self):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""
        if not self.params[0].hasBeenValidated:
            self.params[3].value = _solution_helpers.get_fields(self.params[0])
            fields = json.loads(self.params[3].valueAsText)
            self.params[1].filter.list = [field['name'] for field in fields]
            self.params[1].value = None
            self.params[2].value = None

        if not self.params[1].hasBeenValidated and self.params[0].altered and self.params[3].valueAsText not in ["Failed to connect", "Invalid url"]:
            fields = json.loads(self.params[3].valueAsText)
            field = next((i for i in fields if i['name'] == self.params[1].valueAsText), None)
            if field is not None:
                self.params[2].value = field['alias']

    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        if self.params[3].valueAsText == "Invalid URL":
            self.params[0].setErrorMessage("Input layer or table is not a hosted feature service")
        elif self.params[3].valueAsText == "Failed To Connect":
            self.params[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        else:
            self.params[0].clearMessage()
        return

