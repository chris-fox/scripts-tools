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
    type = arcpy.GetParameterAsText(2)
    name = arcpy.GetParameterAsText(3)
    coded_values = arcpy.GetParameter(4)
    min = arcpy.GetParameterAsText(5)
    max = arcpy.GetParameterAsText(6)
    domain = None

    has_error = False
    if type == 'Coded Value':
        if coded_values.rowCount > 0:
            domain = {'type' : 'codedValue', 'name' : name, 'codedValues' : []}
            for i in range(0, coded_values.rowCount):
                code = coded_values.getValue(i, 0)
                value = coded_values.getValue(i, 1)
            
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
        admin_url = _solution_helpers.get_admin_url(arcpy.GetParameterInfo()[0])
        if admin_url == "Invalid URL":
            raise Exception("Input layer or table is not a hosted feature service")
        elif admin_url == "Failed To Connect":
            raise Exception("Unable to connect to the hosted feature service. Ensure that this service is hosted in the active portal and that you are signed in as the owner.")
        token = arcpy.GetSigninToken()
        request_parameters = {'f' : 'json', 'token' : token['token'], 'async' : False}
        update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
        request_parameters['updateDefinition'] = json.dumps(update_defintion)
        resp = _solution_helpers.url_request(admin_url + "/updateDefinition", request_parameters, token['referer'], request_type='POST')
    except Exception as e:
        arcpy.AddError("Failed to update domain: {0}".format(str(e)))

if __name__ == "__main__":
    main()
