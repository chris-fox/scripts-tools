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
import os, traceback, gzip, json, io, uuid, re
from arcgis.gis import *
from arcgis.lyr import *

try:
    from urllib.request import urlopen as urlopen
    from urllib.request import Request as request
    from urllib.parse import urlencode as encode
    import configparser as configparser
    from io import StringIO
# py2
except ImportError:
    from urllib2 import urlopen as urlopen
    from urllib2 import Request as request
    from urllib import urlencode as encode
    import ConfigParser as configparser
    from cStringIO import StringIO

SOLUITIONS_CONFIG_ID = '6d0361ea1b744019a87f3b921afe3006'
ITEM_UPDATE_PROPERTIES = ['title', 'type', 'description', 'snippet', 
                          'spatialReference', 'tags', 'culture',
                        'accessInformation', 'licenseInfo', 'typeKeywords']
IS_RUN_FROM_PRO = False

def _url_request(url, request_parameters, referer, request_type='GET', repeat=0, error_text="Error", raise_on_failure=True):
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
    req.add_header('Referer', referer)

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
            url, request_parameters, referer, request_type, repeat, error_text, raise_on_failure)

    return response_json

def _create_group(target, original_group):
    title = "{0} {1}".format(original_group['title'], str(uuid.uuid4()).replace('-',''))
    original_group['tags'].append("source-{0}".format(original_group['id']))
    tags = ','.join(original_group['tags'])
    new_group = target.groups.create(title, tags, original_group['description'], original_group['snippet'],
                                     original_group['access'], original_group.get_thumbnail_link(), original_group['isInvitationOnly'],
                                     original_group['sortField'], original_group['sortOrder'], original_group['isViewOnly'])

    return new_group

def _create_service(target, original_feature_service, folder_id=None, sharing=None):
    original_item = original_feature_service.item
    fs_url = original_feature_service.url
    request_parameters = {'f' : 'json'}
    fs_json = _url_request(fs_url, request_parameters, target._portal.con._referer)

    new_name = "{0}_{1}".format(original_item.name, str(uuid.uuid4()).replace('-',''))
    new_item = target.content.create_service(new_name, fs_json['serviceDescription'], 
                                             fs_json['hasStaticData'], fs_json['maxRecordCount'], 
                                             fs_json['supportedQueryFormats'], fs_json['capabilities'],
                                             fs_json['description'], fs_json['copyrightText'],
                                             fs_json['spatialReference']['wkid'], 'featureService', None, folder_id)    

    item_properties = {}
    for property_name in ITEM_UPDATE_PROPERTIES:
        item_properties[property_name] = original_item[property_name]

    item_properties['tags'].append("source-{0}".format(original_item.id))
    item_properties['tags'] = ','.join(item_properties['tags'])
    item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])
    try:
        item_properties['text'] = original_item.get_data() #Bug, throws exception if item contains no data
    except:
        pass

    with tempfile.TemporaryDirectory() as temp_dir:
        thumbnail = original_item.download_thumbnail(temp_dir)
        # TODO updating the metadata changes the tags, need to investigate
        #metadata = original_item.download_metadata(temp_dir)     
        new_item.update(item_properties=item_properties)           
              
    layers_json = _url_request(fs_url + '/layers', request_parameters, target._portal.con._referer)

    # Need to remove relationships first and add them back individually 
    # after all layers and tables have been added to the definition
    relationships = {} 
    for table in layers_json['tables']:
        if 'relationships' in table and len(table['relationships']) != 0:
            relationships[table['id']] = table['relationships']
            table['relationships'] = []
     
    for lyr in layers_json['layers']:
        if 'relationships' in lyr and len(lyr['relationships']) != 0:
            relationships[lyr['id']] = lyr['relationships']
            lyr['relationships'] = []

    definition = json.dumps(layers_json, sort_keys=True) # Layers needs to come before Tables or it effects the output service
    new_feature_service = FeatureService(new_item)
    new_fs_url = new_feature_service.url

    find_string = "/rest/services"
    index = new_fs_url.find(find_string)
    admin_url = '{0}/rest/admin/services{1}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):])
    request_parameters = {'f' : 'json', 'addToDefinition' : definition, 'token' : target._portal.con.token}
    _url_request(admin_url, request_parameters, target._portal.con._referer, 'POST')

    for id in relationships:
        relationships_param = {'relationships' : relationships[id]}
        request_parameters = {'f' : 'json', 'addToDefinition' : json.dumps(relationships_param), 'token' : target._portal.con.token}
        admin_url = '{0}/rest/admin/services{1}/{2}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):], id)
        _url_request(admin_url, request_parameters, target._portal.con._referer, 'POST')

    if sharing is not None:
        _update_sharing(new_item, sharing)
    
    return new_item

def _create_webmap(target, original_item, service_mapping, folder_name=None, sharing=None):  
    #TODO check on properties that should be written
    item_properties = {}
    for property_name in ITEM_UPDATE_PROPERTIES:
        item_properties[property_name] = original_item[property_name]

    item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))
    item_properties['tags'].append("source-{0}".format(original_item.id))
    item_properties['tags'] = ','.join(item_properties['tags'])
    item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])

    webmap_json = original_item.get_data()

    for service in service_mapping:
        url_pattern = re.compile(service[0][1], re.IGNORECASE)
        if 'operationalLayers' in webmap_json:
            for layer in webmap_json['operationalLayers']:
                if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                    if 'itemId' in layer: #swizzle item ids of layers
                        if layer['itemId'].lower() == service[0][0]:
                            layer['itemId'] = service[1][0]
                    if 'url' in layer: #swizzle urls of layers
                        layer['url'] = url_pattern.sub(service[1][1], layer['url'])
        if 'tables' in webmap_json:
            for table in webmap_json['tables']:
                if 'itemId' in table: #swizzle item ids of tables
                    if table['itemId'].lower() == service[0][0]:
                        table['itemId'] = service[1][0]
                if 'url' in table: #swizzle urls of tables
                    table['url'] = url_pattern.sub(service[1][1], table['url'])

    item_properties['text'] = json.dumps(webmap_json)

    with tempfile.TemporaryDirectory() as temp_dir: 
        thumbnail_file = original_item.download_thumbnail(temp_dir)

        # Add the item to the target portal
        new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail_file, folder=folder_name)

    if sharing is not None:
        _update_sharing(new_item, sharing)

    return new_item

def _create_app(target, original_item, service_mapping, webmap_mapping, group_mapping, folder_name=None, sharing=None):  
    item_properties = {}
    for property_name in ITEM_UPDATE_PROPERTIES:
        item_properties[property_name] = original_item[property_name]

    item_properties['tags'].append("source-{0}".format(original_item.id))
    item_properties['tags'] = ','.join(item_properties['tags'])
    item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])

    app_json = original_item.get_data()
    app_json_text = ''

    if "Web AppBuilder" in original_item['typeKeywords']: #Web AppBuilder
        if 'portalUrl' in app_json:
            app_json['portalUrl'] = target._url
        if 'map' in app_json:
            if 'portalUrl' in app_json['map']:
                app_json['map']['portalUrl'] = target._url
            if 'itemId' in app_json['map']:
                app_json['map']['itemId'] = webmap_mapping[app_json['map']['itemId']]
        if 'httpProxy' in app_json:
            if 'url' in app_json['httpProxy']:
                app_json['httpProxy']['url'] = target._url + "sharing/proxy"
        
        app_json_text = json.dumps(app_json)        
        for service in service_mapping:
            url_pattern = re.compile(service[0][1], re.IGNORECASE)
            app_json_text = url_pattern.sub(service[1][1], app_json_text)
        item_properties['text'] = app_json_text

    elif original_item['type'] == "Operation View": #Operations Dashboard
        if 'widgets' in app_json:
            for widget in app_json['widgets']:
                if 'mapId' in widget:
                    widget['mapId'] = webmap_mapping[widget['mapId']]
        item_properties['text'] = json.dumps(app_json)

    else: #Configurable Application Template
        if 'folderId' in app_json:
            output_folder_id = target._portal.get_folder_id(target._username, folder_name)
            app_json['folderId'] = output_folder_id
        if 'values' in app_json:
            if 'group' in app_json['values']:
                app_json['values']['group'] = group_mapping[app_json['values']['group']]
            if 'webmap' in app_json['values']:
                app_json['values']['webmap'] = webmap_mapping[app_json['values']['webmap']]
        #if 'source' in app_json and 'source' == '931653256fd24301a84fc77955914a82': #GeoForm
        #    Bug in GeoForm, https://github.com/Esri/geoform-template-js/issues/511
        item_properties['text'] = json.dumps(app_json)

    with tempfile.TemporaryDirectory() as temp_dir: 
        thumbnail_file = original_item.download_thumbnail(temp_dir)

        # Add the item to the target portal
        new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail_file, folder=folder_name)

    if original_item['url'] is not None:
        find_string = "/apps/"
        index = original_item['url'].find(find_string)
        new_url = '{0}{1}'.format(target._url.rstrip('/'), original_item['url'][index:])
        find_string = "id="
        index = new_url.find(find_string)
        new_url = '{0}{1}'.format(new_url[:index + len(find_string)], new_item.id)
        item_properties = {'url' : new_url}
        new_item.update(item_properties)

    if sharing is not None:
        _update_sharing(new_item, sharing)

    return new_item

def _update_sharing(item, sharing):
        everyone = sharing['access'].lower() == 'public'
        org = sharing['access'].lower() == 'org'
        groups = ''
        if 'groups' in sharing:
            groups = ','.join(sharing['groups'])
        item.share(everyone, org, groups)
        
def _get_existing_item(target, source_id, folder_id, type):
    search_query = 'owner:{0} AND tags:"source-{1}" AND type:{2}'.format(target._username, source_id, type)
    items = target.content.search(search_query)
    for item in items:
        if item['ownerFolder'] == folder_id:
            return item
    return None 

def _move_progressor():
    if IS_RUN_FROM_PRO: #only use arcpy if we are running within Pro 
        import arcpy
        arcpy.SetProgressorPosition()

def _add_message(message):
    if IS_RUN_FROM_PRO: #only use arcpy if we are running within Pro 
        import arcpy
        arcpy.AddMessage(message)
    else:
        print(message)

def _main(target, solution_group, solution_names, output_folder):
    source = GIS()
    solutions_config_json = json.loads(source.content.get(SOLUITIONS_CONFIG_ID).get_data(False).decode('utf-8'))
    group_mapping = {}   
    service_mapping = []
    webmap_mapping = {}   
    
    #TODO Using private methods to get/create folders
    output_folder_id = target._portal.get_folder_id(target._username, output_folder)
    if output_folder_id is None:
        output_folder_id = target._portal.create_folder(target._username, output_folder)['id']

    for solution_name in solution_names:
        if solution_name not in solutions_config_json[solution_group]:
            continue

        solution_items = solutions_config_json[solution_group][solution_name]
        message = 'Deploying {0}'.format(solution_name)
        _add_message(message) 

        if IS_RUN_FROM_PRO:
            import arcpy
            item_count = len([type for type in solution_items for item in solution_items[type]])
            arcpy.SetProgressor('step', message, 0, item_count, 1)

        if 'groups' in solution_items:
            groups = solution_items['groups']
            for group_name in groups:
                original_group_id = groups[group_name]['id']
                if original_group_id in group_mapping:
                    continue
                
                original_group = source.groups.get(original_group_id)
                new_group = _create_group(target, original_group)
                if new_group is not None:
                    _add_message("Created group '{0}'".format(new_group['title']))
                    group_mapping[original_group['id']] = new_group['id']
                _move_progressor()

        if 'services' in solution_items:
            services = solution_items['services']
            for service_name in services:
                original_item = source.content.get(services[service_name]['id']) 
                if original_item.type != 'Feature Service':
                    continue

                original_feature_service = FeatureService(original_item)

                new_item = _get_existing_item(target, original_item.id, output_folder_id, 'Feature Service')
                if new_item is None:
                    sharing = services[service_name]['sharing']
                    if 'groups' in sharing:
                        for group in sharing['groups']:
                            if group in group_mapping:
                                sharing['groups'].remove(group)
                                sharing['groups'].append(group_mapping[group])
                            else:
                                continue #TODO, need to handle this situation, error?
                            
                    new_item = _create_service(target, original_feature_service, output_folder_id, sharing)
                    if new_item is None:
                        continue
                    _add_message("Created service '{0}'".format(new_item['title']))   
                else:
                    _add_message("Existing service '{0}' found in {1}".format(new_item['title'], output_folder))          
                new_feature_service = FeatureService(new_item)
                service_mapping.append([(original_item.id, original_feature_service.url),
                                            (new_item.id, new_feature_service.url)])
                _move_progressor()

        if 'maps' in solution_items:
            maps = solution_items['maps']
            for map_name in maps:
                original_item = source.content.get(maps[map_name]['id']) 
                new_item = _get_existing_item(target, original_item.id, output_folder_id, 'Web Map')
                if new_item is None:
                    sharing = maps[map_name]['sharing']
                    if 'groups' in sharing:
                        for group in sharing['groups']:
                            if group in group_mapping:
                                sharing['groups'].remove(group)
                                sharing['groups'].append(group_mapping[group])
                            else:
                                continue #TODO, need to handle this situation, error?
                    
                    new_item = _create_webmap(target, original_item, service_mapping, output_folder, sharing)
                    if new_item is None:
                        continue
                    _add_message("Created map '{0}'".format(new_item['title']))
                else:
                    _add_message("Existing map '{0}' found in {1}".format(new_item['title'], output_folder))  
                webmap_mapping[original_item.id] =  new_item.id
                _move_progressor()

        if 'apps' in solution_items:
            apps = solution_items['apps']
            for app_name in apps:
                original_item = source.content.get(apps[app_name]['id']) 
                new_item = _get_existing_item(target, original_item.id, output_folder_id, original_item['type'])
                if new_item is None:
                    sharing = apps[app_name]['sharing']
                    if 'groups' in sharing:
                        for group in sharing['groups']:
                            if group in group_mapping:
                                sharing['groups'].remove(group)
                                sharing['groups'].append(group_mapping[group])
                            else:
                                continue #TODO, need to handle this situation, error?
                        
                    new_item = _create_app(target, original_item, service_mapping, webmap_mapping, group_mapping, output_folder, sharing)
                    if new_item is None:
                        continue
                    _add_message("Created application '{0}'".format(new_item['title']))
                else:
                    _add_message("Existing application '{0}' found in {1}".format(new_item['title'], output_folder)) 
                _move_progressor()          

        _add_message('Successfully added {0}'.format(solution_name))
        _add_message('------------------------')

def run(poral_url, username, pw, solution_group, solution_names, output_folder):
    target = GIS(portal_url, pw)
    IS_RUN_FROM_PRO = False
    _main(target, solution_group, solution_names, output_folder)

if __name__ == "__main__":
    target = GIS('pro')
    target._username = json.loads(arcpy.GetPortalDescription())['user']['username']
    target._url = arcpy.GetActivePortalURL()
    solution_group = arcpy.GetParameterAsText(0)
    solution_names = arcpy.GetParameter(1)
    output_folder = arcpy.GetParameterAsText(2)
    IS_RUN_FROM_PRO = True

    _main(target, solution_group, solution_names, output_folder)