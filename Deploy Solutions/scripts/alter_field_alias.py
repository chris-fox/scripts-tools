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
import json, arcpy, _solution_helpers

def main():
    field = arcpy.ListFields(arcpy.GetParameterAsText(0), arcpy.GetParameterAsText(1))[0]
    alias = arcpy.GetParameterAsText(2)
    
    try:
        admin_url = _solution_helpers.get_admin_url(arcpy.GetParameterInfo()[0])
        if admin_url == "Invalid URL":
            raise Exception("Input layer or table is not a hosted feature service")
        elif admin_url == "Failed To Connect":
            raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
        update_defintion = {'fields' : [{'name' : field.name, 'alias' : alias}]}
        request_parameters['updateDefinition'] = json.dumps(update_defintion)
        resp = _solution_helpers.url_request(admin_url + "/updateDefinition", request_parameters, token['referer'], request_type='POST')
    except Exception as e:
        arcpy.AddError("Failed to alter alias: {0}".format(str(e)))

if __name__ == "__main__":
    main()
