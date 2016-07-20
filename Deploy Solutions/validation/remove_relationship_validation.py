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
        if self.params[0].altered:
            relationships = _solution_helpers.get_relationships(self.params[0])
            if relationships == "Invalid URL":
                self.params[0].setErrorMessage("Input layer or table is not a hosted feature service")
            elif relationships == "Failed To Connect":
                self.params[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
            else:
                self.params[0].clearMessage()
                relationships = json.loads(relationships)
                self.params[1].filter.list = [relationship['name'] for relationship in relationships]
                if len(self.params[1].filter.list) == 0:
                    self.params[1].value = None

    def updateMessages(self):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        relationships = _solution_helpers.get_relationships(self.params[0])
        if relationships == "Invalid URL":
            self.params[0].setErrorMessage("Input layer or table is not a hosted feature service")
        elif relationships == "Failed To Connect":
            self.params[0].setErrorMessage("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        else:
            self.params[0].clearMessage()
        
        if self.params[0].altered and len(self.params[1].filter.list) == 0:
            self.params[1].setWarningMessage("Input layer or table has no relationships")
        else:
            self.params[1].clearMessage()
        return

