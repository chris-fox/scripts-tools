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
import arcpy, webbrowser
from arcgis import gis

def main():   
    try:
        url = "{0}/home/webmap/viewer.html?webmap={1}".format(arcpy.GetActivePortalURL(), arcpy.GetParameterAsText(2))
        webbrowser.open(url)
    except Exception as e:
        arcpy.AddError("Failed to open web map: {0}".format(str(e)))

if __name__ == "__main__":
    main()
