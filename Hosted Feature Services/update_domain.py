import arcpy, os, traceback, gzip, json, io

try:
    from urllib.request import urlopen as urlopen
    from urllib.request import Request as request
    from urllib.parse import urlencode as encode
    from urllib.parse import urlparse as parse
    import configparser as configparser
    from io import StringIO
# py2
except ImportError:
    from urllib2 import urlopen as urlopen
    from urllib2 import Request as request
    from urllib import urlencode as encode
    from urlparse import urlparse as parse
    import ConfigParser as configparser
    from cStringIO import StringIO

def _validate_layer_url(parameter):
    try:
        layer = parameter.value
        if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
            return layer.dataSource
        elif arcpy.GetInstallInfo()['ProductName'] == 'ArcGISPro':
            connection_props = layer.connectionProperties
            if connection_props['workspace_factory'] != 'FeatureService':
                return None
            return '{0}/{1}'.format(connection_props['connection_info']['url'], connection_props['dataset'])
    except AttributeError:
        url = layer = parameter.valueAsText
        pieces = parse(url)
        if pieces.scheme in ['http', 'https']:
            return url
        else:
            return None

def _url_request(url, request_parameters, request_type='GET', repeat=0, error_text="Error", raise_on_failure=True):
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
                raise Exception("{0}: {1}".format(error_text, response_json))
            return response_json

        repeat -= 1
        time.sleep(2)
        response_json = self._url_request(
            url, request_parameters, request_type, repeat, error_text, raise_on_failure)

    return response_json

def main():
    field = arcpy.ListFields(arcpy.GetParameterAsText(0), arcpy.GetParameterAsText(1))[0]
    type = arcpy.GetParameterAsText(2)
    name = arcpy.GetParameterAsText(3)
    coded_values = arcpy.GetParameter(4)
    min = arcpy.GetParameter(5)
    max = arcpy.GetParameter(6)
    domain = None

    if type == 'Coded Value':
        domain = {'type' : 'codedValue', 'name' : name, 'codedValues' : []}
        for i in range(0, coded_values.rowCount):
            code = coded_values.getValue(i, 0)
            error_found = False
            if field.type == 'SmallInteger' or field.type == 'Integer':
                try:
                    code = int(code)
                except ValueError:
                    arcpy.AddError("{0} is invalid code for an integer field".format(code))
                    error_found = True
            elif field.type == 'Single' or field.type == 'Double':
                try:
                    code = float(code)
                except ValueError:
                    arcpy.AddError("{0} is invalid code for an floating point field".format(code))
                    error_found = True
            domain['codedValues'].append({'code' : code, 'name' : coded_values.getValue(i, 1)})
        if error_found:
            return
    elif type == 'Range':
        domain = {'type': 'range', 'name' : name, 'range' : [min, max]}

    try:
        url = _validate_layer_url(arcpy.GetParameterInfo()[0])
        find_string = "/rest/services"
        index = url.find(find_string)
        admin_url = '{0}/rest/admin/services{1}/updateDefinition'.format(url[:index], url[index + len(find_string):])
            
        request_parameters = {'f' : 'json', 'token' : arcpy.GetSigninToken()['token'], 'async' : False}
        update_defintion = {'fields' : [{'name' : field.name, 'domain' : domain}]}
        request_parameters['updateDefinition'] = json.dumps(update_defintion)
        _url_request(admin_url, request_parameters, request_type='POST', repeat=2, error_text='Failed to update domain: ')
    except:
        arcpy.AddError(str(sys.exc_info()[1]))

if __name__ == "__main__":
    main()
