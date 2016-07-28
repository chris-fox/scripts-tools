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
import json, uuid, re, tempfile, os, _solution_helpers
from arcgis import gis, lyr

IS_RUN_FROM_PRO = False
TAG = 'one.click.solution'
ITEM_PROPERTY_NAMES = ['title', 'type', 'description', 
                          'snippet', 'tags', 'culture',
                        'accessInformation', 'licenseInfo', 'typeKeywords']

TEXT_BASED_ITEM_TYPES = ['Web Map', 'Feature Service', 'Map Service', 'Operation View',
                                   'Image Service', 'Feature Collection', 'Feature Collection Template',
                                   'Web Mapping Application', 'Mobile Application', 'Symbol Set', 'Color Set']
class SolutionGroup(object):
    def __init__(self, info, thumbnail=None):
        self._info = info
        self._thumbnail = thumbnail

    @property
    def info(self):
        """list of the user's folders"""
        return self._info

    @info.setter
    def info(self, value):
        self._info = value

    @property
    def thumbnail(self):
        """list of the user's folders"""
        return self._thumbnail

    @thumbnail.setter
    def thumbnail(self, value):
        self._thumbnail = value

class SolutionItem(object):
    def __init__(self, info, data=None, sharing=None, thumbnail=None):
        self._info = info
        self._data = data      
        self._sharing = sharing
        self._thumbnail = thumbnail

    @property
    def info(self):
        return self._info

    @info.setter
    def info(self, value):
        self._info = value

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def sharing(self):
        return self._sharing

    @sharing.setter
    def sharing(self, value):
        self._sharing = value

    @property
    def thumbnail(self):
        return self._thumbnail

    @thumbnail.setter
    def thumbnail(self, value):
        self._thumbnail = value

class SolutionTextItem(SolutionItem):
    pass

class SolutionFeatureServiceItem(SolutionTextItem):
    def __init__(self, info, service_definition, layers_definition, data=None, sharing=None, thumbnail=None):
        self._service_definition = service_definition
        self._layers_definition = layers_definition
        super(SolutionTextItem, self).__init__(info, data, sharing, thumbnail)

    @property
    def service_definition(self):
        return self._service_definition

    @service_definition.setter
    def service_definition(self, value):
        self._service_definition = value

    @property
    def layers_definition(self):
        return self._layers_definition

    @layers_definition.setter
    def layers_definition(self, value):
        self._layers_definition = value

class ItemCreateException(Exception):
    pass

def _get_item_properties(item, extent=None):
    item_properties = {}
    for property_name in ITEM_PROPERTY_NAMES:
        item_properties[property_name] = item[property_name]

    item_properties['typeKeywords'].append("source-{0}".format(item['id']))
    if TAG in item_properties['tags']:
        item_properties['tags'].remove(TAG)
        item_properties['typeKeywords'].append(TAG)
    item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])
    item_properties['tags'] = ','.join(item_properties['tags'])   
    item_properties['extent'] = extent

    return item_properties

def _clone_group(connection, solution_group, folder=None):
    """Clone a new group from an existing group.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_group - Existing group to clone
    folder - The folder containing items for the solution to associate with the new group"""
    
    try:
        new_group = None
        target = connection['target']
        original_group = solution_group.info
        
        title = original_group['title']
        original_group['tags'].append("source-{0}".format(original_group['id']))
        if folder:
            original_group['tags'].append("sourcefolder-{0}".format(folder['id']))
        tags = ','.join(original_group['tags'])
    
        #Find a unique name for the group
        i = 1    
        while True:
            search_query = 'owner:{0} AND title:"{1}"'.format(connection['username'], title)
            groups = target.groups.search(search_query, outside_org=False)
            if len(groups) == 0:
                break
            i += 1
            title = "{0} {1}".format(original_group['title'], i)
        
        thumbnail = solution_group.thumbnail
        if not thumbnail and isinstance(original_group, gis.Group):
            thumbnail = original_group.get_thumbnail_link()

        new_group = target.groups.create(title, tags, original_group['description'], original_group['snippet'],
                                         'private', thumbnail, True, original_group['sortField'], original_group['sortOrder'], True)
        return new_group
    except Exception as e:
        raise ItemCreateException("Failed to create group '{0}': {1}".format(original_group['title'], str(e)), new_group)

def _clone_feature_service(connection, solution_feature_service_item, extent, folder=None):
    """Clone a new service in the target portal from the definition of an existing service.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_feature_service - Existing feature service to clone
    extent - Default extent of the new feature service in WGS84
    folder - The folder to create the service in"""

    try:
        new_item = None
        original_item = solution_feature_service_item.info
        target = connection['target']       

        # Get the definition of the original feature service
        service_definition = solution_feature_service_item.service_definition

        # Create a new service from the definition of the original feature service
        for key in ['layers', 'tables']:
            del service_definition[key]     
        service_definition['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))
        url = "{0}sharing/rest/content/users/{1}/".format(connection['url'], connection['username'])
        if folder:
            url += "{0}/".format(folder['id'])
        url += 'createService'
        request_parameters = {'f' : 'json', 'createParameters' : json.dumps(service_definition), 
                              'outputType' : 'featureService', 'token' : connection['token']}
        resp =_solution_helpers.url_request(url, request_parameters, connection['referer'], 'POST')
        new_item = target.content.get(resp['itemId'])        
    
        # Get the layer and table definitions from the original service
        layers_definition = solution_feature_service_item.layers_definition

        # Need to remove relationships first and add them back individually 
        # after all layers and tables have been added to the definition
        relationships = {} 
        for table in layers_definition['tables']:
            if 'relationships' in table and len(table['relationships']) != 0:
                relationships[table['id']] = table['relationships']
                table['relationships'] = []
     
        for layer in layers_definition['layers']:
            if 'relationships' in layer and len(layer['relationships']) != 0:
                relationships[layer['id']] = layer['relationships']
                layer['relationships'] = []

        # Layers needs to come before Tables or it effects the output service
        definition = json.dumps(layers_definition, sort_keys=True) 
        new_fs_url = new_item.url

        # Add the layer and table defintions to the service
        find_string = "/rest/services"
        index = new_fs_url.find(find_string)
        admin_url = '{0}/rest/admin/services{1}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):])
        request_parameters = {'f' : 'json', 'addToDefinition' : definition, 'token' : connection['token']}
        _solution_helpers.url_request(admin_url, request_parameters, connection['referer'], 'POST')

        # Add any releationship defintions back to the layers and tables
        for id in relationships:
            relationships_param = {'relationships' : relationships[id]}
            request_parameters = {'f' : 'json', 'addToDefinition' : json.dumps(relationships_param), 'token' : connection['token']}
            admin_url = '{0}/rest/admin/services{1}/{2}/addToDefinition'.format(new_fs_url[:index], new_fs_url[index + len(find_string):], id)
            _solution_helpers.url_request(admin_url, request_parameters, connection['referer'], 'POST')

        # Update the item definition of the service
        item_properties = _get_item_properties(original_item, extent)
        item_properties['text'] = solution_feature_service_item.data

        with tempfile.TemporaryDirectory() as temp_dir: 
            thumbnail = solution_feature_service_item.thumbnail
            if not thumbnail and isinstance(original_item, gis.Item):
                thumbnail = original_item.download_thumbnail(temp_dir)
            new_item.update(item_properties=item_properties, thumbnail=thumbnail)
    
        # Share the item
        if solution_feature_service_item.sharing:
            _share_item(new_item, solution_feature_service_item.sharing)

        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create service '{0}': {1}".format(original_item['title'], str(e)), new_item)

def _clone_webmap(connection, solution_text_item, service_mapping, extent, folder=None):  
    """Clone a new service in the target portal from the definition of an existing service.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_item - Existing web map to clone
    original_item_data - JSON definition of the web map
    service_mapping - A data structure that contains the mapping between the original service item and url and the new service item and url
    extent - Default extent of the new web map in WGS84
    folder - The folder to create the web map in
    group - The id of the group to share the web map with"""
    
    try:
        new_item = None
        original_item = solution_text_item.info
        target = connection['target']
        
        # Get the item properties from the original web map which will be applied when the new item is created
        item_properties = _get_item_properties(original_item, extent)
        item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))

        # Swizzle the item ids and URLs of the operational layers and tables in the web map
        webmap_json = solution_text_item.data
        for service in service_mapping:
            url_pattern = re.compile(service[0][1], re.IGNORECASE)
            if 'operationalLayers' in webmap_json:
                for layer in webmap_json['operationalLayers']:
                    if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                        if 'itemId' in layer:
                            if layer['itemId'].lower() == service[0][0]:
                                layer['itemId'] = service[1][0]
                        if 'url' in layer:
                            layer['url'] = url_pattern.sub(service[1][1], layer['url'])
            if 'tables' in webmap_json:
                for table in webmap_json['tables']:
                    if 'itemId' in table:
                        if table['itemId'].lower() == service[0][0]:
                            table['itemId'] = service[1][0]
                    if 'url' in table:
                        table['url'] = url_pattern.sub(service[1][1], table['url'])

        # Add the web map to the target portal
        item_properties['text'] = json.dumps(solution_text_item.data)

        with tempfile.TemporaryDirectory() as temp_dir: 
            thumbnail = solution_text_item.thumbnail
            if not thumbnail and isinstance(original_item, gis.Item):
                thumbnail = original_item.download_thumbnail(temp_dir)
            new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail, folder=folder['title'])

        # Share the item
        if solution_text_item.sharing:
            _share_item(new_item, solution_text_item.sharing)

        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create web map '{0}': {1}".format(original_item['title'], str(e)), new_item)

def _clone_app(connection, solution_text_item, service_mapping, webmap_mapping, group_mapping, folder=None):
    """Clone a new application in the target portal from the definition of an existing application.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_item - Existing application to clone
    original_item_data - JSON definition of the application
    service_mapping - A data structure that contains the mapping between the original service item and url and the new service item and url
    webmap_mapping - A dictionary containing a mapping between the original web map id and new web map id
    group_mapping - A dictionary containing a mapping between the original group and the new group
    folder - The folder to create the application in
    group - The id of the group to share the web map with"""  
    
    try:
        new_item = None
        original_item = solution_text_item.info
        target = connection['target']

        # Get the item properties from the original application which will be applied when the new item is created
        item_properties = _get_item_properties(original_item)

        # Swizzle the item ids of the web maps, groups and URLs of definied in the application's data
        app_json = solution_text_item.data
        app_json_text = ''

        if "Web AppBuilder" in original_item['typeKeywords']: #Web AppBuilder
            if 'portalUrl' in app_json:
                app_json['portalUrl'] = connection['url']
            if 'map' in app_json:
                if 'portalUrl' in app_json['map']:
                    app_json['map']['portalUrl'] = connection['url']
                if 'itemId' in app_json['map']:
                    app_json['map']['itemId'] = webmap_mapping[app_json['map']['itemId']]
            if 'httpProxy' in app_json:
                if 'url' in app_json['httpProxy']:
                    app_json['httpProxy']['url'] = connection['url'] + "sharing/proxy"
        
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
                app_json['folderId'] = folder['id']
            if 'values' in app_json:
                if 'group' in app_json['values']:
                    app_json['values']['group'] = group_mapping[app_json['values']['group']]
                if 'webmap' in app_json['values']:
                    app_json['values']['webmap'] = webmap_mapping[app_json['values']['webmap']]
            item_properties['text'] = json.dumps(app_json)

        # Add the application to the target portal
        with tempfile.TemporaryDirectory() as temp_dir: 
            thumbnail = solution_text_item.thumbnail
            if not thumbnail and isinstance(original_item, gis.Item):
                thumbnail = original_item.download_thumbnail(temp_dir)
            new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail, folder=folder['title'])

        # Update the url of the item to point to the new portal and new id of the application
        if original_item['url']:
            find_string = "/apps/"
            index = original_item['url'].find(find_string)
            new_url = '{0}{1}'.format(connection['url'].rstrip('/'), original_item['url'][index:])
            find_string = "id="
            index = new_url.find(find_string)
            new_url = '{0}{1}'.format(new_url[:index + len(find_string)], new_item.id)
            item_properties = {'url' : new_url}
            new_item.update(item_properties)
    
        # Share the item
        if solution_text_item.sharing:
            _share_item(new_item, solution_text_item.sharing)

        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create application '{0}': {1}".format(original_item.title, str(e)), new_item)

def _update_group_sharing(solution_items, group_mapping):
    for item in solution_items:
        if item.sharing and 'groups' in item.sharing:
            for group in item.sharing['groups']:
                if group in group_mapping:
                    item.sharing['groups'].remove(group)
                    item.sharing['groups'].append(group_mapping[group])

def _share_item(item, sharing):
    everyone = sharing['access'] == 'everyone'
    org = sharing['access'] == 'org'
    groups = ''
    if sharing['groups']:
        groups = ','.join(sharing['groups'])
    item.share(everyone, org, groups)

def _get_solution_definition(source, item, solution_definition, groups=[]):
    """Get the children item and item data of a given item. This is used to recursively find all the items that make up a given map or app.
    Keyword arguments:
    source - The portal containing the item
    item - The item to search
    solution_items - a dictionary that will define the groups, services, maps, and apps that make up a solution
    group - The id of the group to share the web map with"""  

    # Check if the item has already been added to the collection
    solution_item = next((i for i in solution_definition['items'] if i.info['id'] == item.id), None)
    if solution_item:
        return

    # If the item is an application or dashboard find the web map or group that the application is built from
    if item['type'] in ['Web Mapping Application','Operation View']:
        app_json = item.get_data()
        
        solution_definition['items'].append(SolutionTextItem(item, data=app_json, sharing={
				"access": "private",
				"groups": groups
					}))
   
        webmap_id = None
        if item['type'].lower() == "operation view": #Operations Dashboard
            if 'widgets' in app_json:
                for widget in app_json['widgets']:
                    if 'mapId' in widget:
                        webmap_id = widget['mapId']
                        break

        elif "Web AppBuilder" in item['typeKeywords']: #Web AppBuilder
            if 'map' in app_json:
                if 'itemId' in app_json['map']:
                    webmap_id = app_json['map']['itemId']

        else: #Configurable Application Template
            if 'values' in app_json:
                if 'group' in app_json['values']:
                    group_id = app_json['values']['group']
                    group = next((g for g in solution_definition['groups'] if g.info['id'] == group_id), None)
                    if not group:
                        group = source.groups.get(group_id)
                        solution_definition['groups'].append(SolutionGroup(group))
                    
                    search_query = 'group:{0} AND type:{1}'.format(group_id, 'Web Map')
                    group_items = source.content.search(search_query, max_items=100, outside_org=True)
                    for webmap in group_items:
                        _get_solution_definition(source, webmap, solution_definition, [group_id])

                if 'webmap' in app_json['values']:
                    webmap_id = app_json['values']['webmap']
        
        if webmap_id:
            webmap = source.content.get(webmap_id)
            _get_solution_definition(source, webmap, solution_definition)

    # If the item is a web map find all the feature service layers and tables that make up the map
    elif item['type'] == 'Web Map':
        webmap_json = item.get_data()
        solution_definition['items'].append(SolutionTextItem(item, data=webmap_json, sharing={
				"access": "private",
				"groups": groups
					}))
        
        if 'operationalLayers' in webmap_json:
            for layer in webmap_json['operationalLayers']:
                if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                    if 'itemId' in layer:
                        feature_service = source.content.get(layer['itemId'])
                        _get_solution_definition(source, feature_service, solution_definition)

        if 'tables' in webmap_json:
            for table in webmap_json['tables']:
                    if 'itemId' in table:
                        feature_service = source.content.get(table['itemId'])
                        _get_solution_definition(source, feature_service, solution_definition)

    # If the item is a feature service get the definition of the service and its layers and tables
    elif item['type'] == 'Feature Service':
        url = item['url']
        request_parameters = {'f' : 'json'}
        service_definition = _solution_helpers.url_request(url, request_parameters)
        layers_defintion = _solution_helpers.url_request(url + '/layers', request_parameters)
        data = item.get_data()
        solution_definition['items'].append(SolutionFeatureServiceItem(item, service_definition, layers_defintion, data, {
				    "access": "private",
				    "groups": groups
					    }))
    
    # All other item types
    else:
        if item['type'] in TEXT_BASED_ITEM_TYPES:
            item_definition['data'] = item.get_data()
            solution_definition['items'].append(SolutionTextItem(item, item.item.get_data(), {
			"access": "private",
			"groups": groups
				}))
        else:
            solution_definition['items'].append(SolutionItem(item, {
			"access": "private",
			"groups": groups
				}))

def _get_local_solution_definition(map_app, local_definitions, solution_definition):
    solutions_definition_file = os.path.join(local_definitions, 'SolutionDefinitions.json') 
    definitions = None
    if os.path.exists(solutions_definition_file):
        with open(solutions_definition_file, 'r') as file:
            content = file.read() 
            definitions = json.loads(content)
    
    if not definitions:
        return

    items_directory = os.path.join(local_definitions, 'items')

    for item_id in definitions['MapsAndApps'][map_app]['items']:
        item_directory = os.path.join(items_directory, item_id)
        if not os.path.exists(item_directory):
            continue

        solution_item = None
        data = next((os.path.join(item_directory, f) for f in os.listdir(item_directory) if os.path.isfile(os.path.join(item_directory, f))),None)

        esriinfo_directory = os.path.join(item_directory, 'esriinfo')
        iteminfo = os.path.join(esriinfo_directory, 'iteminfo.json')
        with open(iteminfo, 'r') as file:
            content = file.read() 
            item = json.loads(content)
        if item['info']['type'] in TEXT_BASED_ITEM_TYPES:
            with open(data, 'r') as file:
                content = file.read() 
                data = json.loads(content)
            if item['info']['type'] == 'Feature Service':
                featureserver = os.path.join(esriinfo_directory, 'featureserver.json')
                with open(featureserver, 'r') as file:
                    content = file.read() 
                    featureserver = json.loads(content)
                    solution_item = SolutionFeatureServiceItem(item['info'], featureserver['serviceDefinition'], featureserver['layersDefinition'], data, item['sharing'])
            else:
                solution_item = SolutionTextItem(item['info'], data, item['sharing'])
        else:
            solution_item = SolutionItem(item['info'], data, item['sharing'])

        thumbnail_directory = os.path.join(esriinfo_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_item.thumbnail = thumbnail

        solution_definition['items'].append(solution_item)

    for group_id in definitions['MapsAndApps'][map_app]['groups']:
        group_directory = os.path.join(items_directory, 'groupinfo', group_id)
        if not os.path.exists(group_directory):
            continue

        solution_group = None
        groupinfo = os.path.join(group_directory, 'groupinfo.json')
        with open(groupinfo, 'r') as file:
            content = file.read() 
            group = json.loads(content)
            solution_group = SolutionGroup(group)

        thumbnail_directory = os.path.join(group_directory, 'thumbnail')
        if os.path.exists(thumbnail_directory):
            thumbnail = next((os.path.join(thumbnail_directory, f) for f in os.listdir(thumbnail_directory) if os.path.isfile(os.path.join(thumbnail_directory, f))),None)
            solution_group.thumbnail = thumbnail

        solution_definition['groups'].append(solution_group)

def _write_solution_items(solution_name, map_app_name, solution_definition, output_directory):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    solutions_definition_file = os.path.join(output_directory, 'SolutionDefinitions.json') 
    if not os.path.exists(solutions_definition_file):
        file = open(solutions_definition_file, "w")
        file.close
    
    with open(solutions_definition_file, 'r+') as file:
        content = file.read()  
        file.seek(0)   
        definitions = {'Solutions' : {}, 'MapsAndApps' : {} }
        if not content == '':
            definitions = json.loads(content)

        if solution_name not in definitions['Solutions']:
            definitions['Solutions'][solution_name] = []

        if map_app_name not in definitions['Solutions'][solution_name]:
            definitions['Solutions'][solution_name].append(map_app_name)

        definitions['MapsAndApps'][map_app_name] = {'items' : [], 'groups' : []}

        for item in solution_definition['items']:
            definitions['MapsAndApps'][map_app_name]['items'].append(item.info['id'])

        for group in solution_definition['groups']:
            definitions['MapsAndApps'][map_app_name]['groups'].append(group.info['id'])

        file.write(json.dumps(definitions))
        file.truncate()

    items_directory = os.path.join(output_directory, 'items')
    if not os.path.exists(items_directory):
        os.makedirs(items_directory)

    for item in solution_definition['items']:
        item_id = item.info['id']
        item_directory =  os.path.join(items_directory, item_id)
        if os.path.exists(item_directory):
            _add_message("Existing item {0}, {1} already downloaded".format(item.info['title'], item.info['id']))
            _move_progressor() 
            continue

        os.makedirs(item_directory)
        if isinstance(item, SolutionTextItem):
            data_json = os.path.join(item_directory, item_id + '.json')
            with open(data_json, 'w') as file:
                file.write(json.dumps(item.data))
        else:
            item.info.download(item_directory)

        esriinfo_directory = os.path.join(item_directory, 'esriinfo')
        os.makedirs(esriinfo_directory)
        iteminfo_json = os.path.join(esriinfo_directory, 'iteminfo.json')
        with open(iteminfo_json, 'w') as file:
            file.write(json.dumps({'info' : item.info, 'sharing' : item.sharing }))

        if isinstance(item, SolutionFeatureServiceItem):
            featureserver_json = os.path.join(esriinfo_directory, "featureserver.json")
            with open(featureserver_json, 'w') as file:
                file.write(json.dumps({'serviceDefinition' : item.service_definition, 'layersDefinition' : item.layers_definition}))

        thumbnail_directory = os.path.join(esriinfo_directory, 'thumbnail')
        os.makedirs(thumbnail_directory)
        thumbnail = item.info.download_thumbnail(thumbnail_directory)
        if not thumbnail:
            os.rmdir(thumbnail_directory)

        _add_message("Downloaded item {0}, {1}".format(item.info['title'], item.info['id']))
        _move_progressor() 

    for group in solution_definition['groups']:
        groupinfo_directory = os.path.join(items_directory, 'groupinfo')
        if not os.path.exists(groupinfo_directory):
            os.makedirs(groupinfo_directory)

        group_directory = os.path.join(groupinfo_directory, group.info['id'])
        if os.path.exists(group_directory):
            _add_message("Existing group {0}, {1} already downloaded".format(group.info['title'], group.info['id']))
            _move_progressor() 
            continue

        os.makedirs(group_directory)
        group_json = os.path.join(group_directory, 'groupinfo.json')
        with open(group_json, 'w') as file:
            file.write(json.dumps(group.info))

        thumbnail_directory = os.path.join(group_directory, 'thumbnail')
        os.makedirs(thumbnail_directory)
        thumbnail = group.info.download_thumbnail(thumbnail_directory)
        if not thumbnail:
            os.rmdir(thumbnail_directory)

        _add_message("Downloaded group {0}, id: {1}".format(group.info['title'], group.info['id']))
        _move_progressor() 

def _get_existing_item(item, folder_items):
    """Test if an item with a given source tag already exists in the user's content. 
    This is used to determine if the service, map or app has already been created in the folder.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    source_id - Item id of the original item that is going to be cloned
    folder - The folder to search for the item within
    type - Type of item we are searching for"""  
   
    return next((folder_item for folder_item in folder_items if folder_item['type'] == item['type'] 
                          and "source-{0}".format(item['id']) in folder_item['typeKeywords']), None)

def _get_existing_group(connection, group_id, folder):
    """Test if a group with a given source tag already exists in the organization. 
    This is used to determine if the group has already been created 
    and if new maps and apps that belong to the same group should be shared to the same group.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    source_id - Item id of the original folder that is going to be cloned
    folder - The folder that is used as a tag on the group indicating new items created in the same folder should share the group""" 
    
    target = connection['target']
    search_query = 'owner:{0} AND tags:"source-{1},sourcefolder-{2}"'.format(connection['username'], group_id, folder['id']) 
    groups = target.groups.search(search_query, outside_org=False)
    if len(groups) > 0:
        return groups[0]
    return None

def _move_progressor():
    """Move the progressor when the tool is running in ArcGIS Pro"""
    if IS_RUN_FROM_PRO: #only use arcpy if we are running within Pro 
        import arcpy
        arcpy.SetProgressorPosition()

def _add_message(message, type='Info'):
    """Add a message to the output"""
    if IS_RUN_FROM_PRO: #only use arcpy if we are running within Pro 
        import arcpy
        if type == 'Info':
            arcpy.AddMessage(message)
        elif type == 'Warning':
            arcpy.AddWarning(message)
        elif type == 'Error':
            arcpy.AddError(message)
    else:
        print(message)

def _download_solutions(connection, solution, maps_apps, output_folder):
    target = connection['target']

    for map_app_name in maps_apps:
        try:
            # Search for the map or app in the given organization using the map or app name and a specific tag
            search_query = 'tags:"{0},solution.{1}" AND title:"{2}"'.format(TAG, solution, map_app_name)
            solutions = {}
            items = target.content.search(search_query, outside_org=True)
            item = next((item for item in items if item.title == map_app_name), None)
            if not item:
                continue

            # Get the definitions of the services, groups, maps and apps that make up the solution
            solution_definition = { 'items' : [], 'groups' : [] }
            _get_solution_definition(target, item, solution_definition)
            message = 'Downloading {0}'.format(map_app_name)
            _add_message(message) 

            # If run from the application set the progressor
            if IS_RUN_FROM_PRO:
                import arcpy
                item_count = len(solution_definition['items']) + len(solution_definition['groups'])
                arcpy.SetProgressor('step', message, 0, item_count, 1)

            # Write the solution items
            _write_solution_items(solution, map_app_name, solution_definition, output_folder)

            _add_message('Successfully downloaded {0}'.format(map_app_name))
            _add_message('------------------------')
        except Exception as e:
            _add_message('Failed to download {0}: {1}'.format(map_app_name, str(e)), 'Error')
            _add_message('------------------------')

def _create_solutions(connection, solution, maps_apps, extent, output_folder, local_definitions=None):
    """Clone a collection of maps and apps into a new portal
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    solution - The name of the solution
    maps_apps - A list of maps and apps that have a particular tag to be cloned into the portal
    extent - The default extent of the new maps and services in WGS84
    output_folder - The name of the folder to create the new items within the user's content""" 

    target = connection['target']
    if not local_definitions:
        source = gis.GIS()

    group_mapping = {}   
    service_mapping = []
    webmap_mapping = {}   
    
    # If the folder does not already exist create a new folder
    current_user = target.users.me
    folders = current_user.folders
    folder = next((folder for folder in folders if folder['title'] == output_folder), None)
    if not folder:
        folder = target.content.create_folder(output_folder)
    
    # Get the all items in the folder
    folder_items = current_user.items(folder['title'])

    for map_app_name in maps_apps:
        try:
            created_items = []
            solution_definition = { 'items' : [], 'groups' : [] }

            if not local_definitions:
                # Search for the map or app in the given organization using the map or app name and a specific tag
                search_query = 'accountid:{0} AND tags:"{1},solution.{2}" AND title:"{3}"'.format(_solution_helpers.PORTAL_ID, TAG, solution, map_app_name)
                solutions = {}
                items = source.content.search(search_query)
                item = next((item for item in items if item.title == map_app_name), None)
                if not item:
                    continue

                # Check if the item has already been cloned into the target portal and if so, continue on to the next map or app.
                existing_item = _get_existing_item(item, folder_items)
                if existing_item:
                    _add_message("'{0}' already exists in {1} folder".format(item.title, folder['title']))
                    _add_message('------------------------')
                    continue

                # Get the definitions of the services, groups, maps and apps that make up the solution
                _get_solution_definition(source, item, solution_definition)
            else:
                # Get the definitions of the services, groups, maps and apps that make up the solution
                _get_local_solution_definition(map_app_name, local_definitions, solution_definition)

            message = 'Deploying {0}'.format(map_app_name)
            _add_message(message) 

            # If run from the application set the progressor
            if IS_RUN_FROM_PRO:
                import arcpy
                item_count = len(solution_definition['items']) + len(solution_definition['groups'])
                arcpy.SetProgressor('step', message, 0, item_count, 1)

            # Process and clone the groups that don't already exist
            for group in solution_definition['groups']:
                original_group = group.info

                if original_group['id'] in group_mapping: #We have already found or created this item
                    _add_message("Existing group '{0}' found".format(original_group['title']))
                    _move_progressor()
                    continue
                
                new_group = _get_existing_group(connection, original_group['id'], folder)
                if not new_group:
                    new_group = _clone_group(connection, group, folder)
                    created_items.append(new_group)
                    _add_message("Created group '{0}'".format(new_group['title']))
                else:
                    _add_message("Existing group '{0}' found".format(new_group['title']))
                group_mapping[original_group['id']] = new_group['id']
                _move_progressor()

            #Update the group sharing definition for items using the new group ids
            _update_group_sharing(solution_definition['items'], group_mapping)

            # Process and clone the feature services that don't already exist
            for feature_service in [item for item in solution_definition['items'] if item.info['type']== 'Feature Service']:
                original_item = feature_service.info

                if original_item['id'] in [service_map[0][0] for service_map in service_mapping]: #We have already found or created this item
                    _add_message("Existing service '{0}' found in {1} folder".format(original_item['title'], folder['title'])) 
                    _move_progressor()
                    continue

                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:                     
                    new_item = _clone_feature_service(connection, feature_service, extent, folder)
                    created_items.append(new_item)
                    folder_items.append(new_item)
                    _add_message("Created service '{0}'".format(new_item['title']))   
                else:
                    _add_message("Existing service '{0}' found in {1} folder".format(new_item.title, folder['title']))          
                service_mapping.append([(original_item['id'], original_item['url']),
                                            (new_item['id'], new_item['url'])])
                _move_progressor()

            # Process and clone the web maps that don't already exist
            for webmap in [item for item in solution_definition['items'] if item.info['type'] == 'Web Map']:
                original_item = webmap.info

                if original_item['id'] in webmap_mapping: #We have already found or created this item
                    _add_message("Existing map '{0}' found in {1} folder".format(original_item['title'], folder['title']))  
                    _move_progressor()
                    continue
          
                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:
                    new_item = _clone_webmap(connection, webmap, service_mapping, extent, folder)
                    created_items.append(new_item)
                    folder_items.append(new_item)
                    _add_message("Created map '{0}'".format(new_item['title']))
                else:
                    _add_message("Existing map '{0}' found in {1} folder".format(new_item['title'], folder['title']))  
                webmap_mapping[original_item['id']] =  new_item['id']
                _move_progressor()

            # Process and clone the apps that don't already exist
            for application in [item for item in solution_definition['items'] if item.info['type'] in ['Web Mapping Application','Operation View']]:
                original_item = application.info

                new_item = _get_existing_item(original_item, folder_items)
                if not new_item:                   
                    new_item = _clone_app(connection, application, service_mapping, webmap_mapping, group_mapping, folder)
                    created_items.append(new_item)
                    folder_items.append(new_item)
                    _add_message("Created application '{0}'".format(new_item['title']))
                else:
                    _add_message("Existing application '{0}' found in {1} folder".format(new_item['title'], folder['title'])) 
                _move_progressor()          

            _add_message('Successfully added {0}'.format(map_app_name))
            _add_message('------------------------')

        except Exception as e:
            if type(e) == ItemCreateException:
                _add_message(e.args[0], 'Error')
                if e.args[1]:
                    created_items.append(e.args[1])
            else:
                _add_message(str(e), 'Error')

            for item in created_items:
                if item.delete():
                    _add_message("Deleted {0}".format(item.title))
            _add_message('Failed to add {0}'.format(map_app_name), 'Error')
            _add_message('------------------------')

def download_solutions(portal_url, username, pw, solution, maps_apps, output_folder):
    target = gis.GIS(portal_url, username, pw)
    connection = {'target' : target, 'url' : portal_url, 
                'username' : username, 
                'token' : target._portal.con.token, 
                'referer' : target._portal.con._referer }
    IS_RUN_FROM_PRO = False
    _download_solutions(connection, solution, maps_apps, output_folder)

def create_solutions(portal_url, username, pw, solution, maps_apps, extent, output_folder, local_definitions=None):
    """Clone a collection of maps and apps into a new portal
    Keyword arguments:
    portal_url - URL of the portal to clone the solutions to
    username - Username of the user used to create new items
    pw - Password of the user used to create new items
    solution - The name of the solution
    maps_apps - A list of maps and apps that have a particular tag to be cloned into the portal
    extent - The default extent of the new maps and services in WGS84
    output_folder - The name of the folder to create the new items within the user's content""" 
    
    target = gis.GIS(portal_url, username, pw)
    connection = {'target' : target, 'url' : portal_url, 
                'username' : username, 
                'token' : target._portal.con.token, 
                'referer' : target._portal.con._referer }
    IS_RUN_FROM_PRO = False
    _create_solutions(connection, solution, maps_apps, extent, output_folder, local_definitions)

if __name__ == "__main__":  
    connection = None
    try:
        # Specify that we are running within Pro
        # We will only leverage arcpy in this case to get/set parameters, add messages to the tool output, and set the progressor
        IS_RUN_FROM_PRO = True
        import arcpy

        # Setup the target portal using the active portal within Pro
        target = gis.GIS('pro')
        token = arcpy.GetSigninToken()
        connection = {'target' : target, 'url' : arcpy.GetActivePortalURL(), 
                      'username' : target.users.me.username, 
                      'token' : token['token'], 'referer' : token['referer'] }
    except Except:
        arcpy.AddError("Unable to connect to the active portal. Please ensure you are logged into the active portal and that it is the portal you wish to deploy the maps and apps to.")

    if connection:
        mode = arcpy.GetParameterAsText(0)

        if mode == 'DOWNLOAD':
            solution = arcpy.GetParameterAsText(1)
            maps_apps = sorted(list(set(arcpy.GetParameter(2)))) 
            output_folder = arcpy.GetParameterAsText(3)
            arcpy.SetParameterAsText(4, '')
            _download_solutions(connection, solution, maps_apps, output_folder)

        else:
            if mode == 'CREATE':
                # Get the input parameters
                local_definitions = None
                solution = arcpy.GetParameterAsText(1)
                maps_apps = sorted(list(set(arcpy.GetParameter(2)))) 
                extent = arcpy.GetParameter(3)
                output_folder = arcpy.GetParameterAsText(4)
                arcpy.SetParameterAsText(5, '')
            else:
                # Get the input parameters
                local_definitions = arcpy.GetParameterAsText(1)
                solution = arcpy.GetParameterAsText(2)
                maps_apps = sorted(list(set(arcpy.GetParameter(3)))) 
                extent = arcpy.GetParameter(4)
                output_folder = arcpy.GetParameterAsText(5)

            # Get the default extent of new maps defined in the portal
            if not extent:
                portal_description = json.loads(arcpy.GetPortalDescription())
                default_extent = portal_description['defaultExtent']
                coordinates = [[default_extent['xmin'], default_extent['ymin']], 
                        [default_extent['xmax'], default_extent['ymin']], 
                        [default_extent['xmax'], default_extent['ymax']], 
                        [default_extent['xmin'], default_extent['ymax']], 
                        [default_extent['xmin'], default_extent['ymin']]]

                polygon = arcpy.Polygon(arcpy.Array([arcpy.Point(*coords) for coords in coordinates]), 
                                        arcpy.SpatialReference(default_extent['spatialReference']['wkid']))
                extent = polygon.extent

            # Project the extent to WGS84 which is used by default for the web map and services initial extents
            extent_wgs84 = extent.projectAs(arcpy.SpatialReference(4326))
            extent_text = '{0},{1},{2},{3}'.format(extent_wgs84.XMin, extent_wgs84.YMin, 
                                                        extent_wgs84.XMax, extent_wgs84.YMax)
    
            # Clone the solutions
            _create_solutions(connection, solution, maps_apps, extent_text, output_folder, local_definitions)


