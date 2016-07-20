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
import json, uuid, re, tempfile, _solution_helpers
from arcgis import gis, lyr

ITEM_UPDATE_PROPERTIES = ['title', 'type', 'description', 
                          'snippet', 'tags', 'culture',
                        'accessInformation', 'licenseInfo', 'typeKeywords']
IS_RUN_FROM_PRO = False

class ItemCreateException(Exception):
    pass

def _clone_group(connection, original_group, folder=None):
    """Clone a new group from an existing group.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_group - Existing group to clone
    folder - The folder containing items for the solution to associate with the new group"""
    
    try:
        new_group = None
        target = connection['target']
        
        title = original_group.title
        original_group.tags.append("source-{0}".format(original_group.id))
        if folder is not None:
            original_group.tags.append("sourcefolder-{0}".format(folder['id']))
        tags = ','.join(original_group.tags)
    
        #Find a unique name for the group
        i = 1    
        while True:
            search_query = 'owner:{0} AND title:"{1}"'.format(connection['username'], title)
            groups = target.groups.search(search_query, outside_org=False)
            if len(groups) == 0:
                break
            i += 1
            title = "{0} {1}".format(original_group.title, i)

        new_group = target.groups.create(title, tags, original_group.description, original_group.snippet,
                                         'private', original_group.get_thumbnail_link(), True,
                                         original_group.sortField, original_group.sortOrder, True)
        if new_group is None:
            raise Exception()

        return new_group
    except Exception as e:
        raise ItemCreateException("Failed to create group '{0}': {1}".format(original_group.title, str(e)), new_group)

def _clone_service(connection, original_feature_service, extent, folder=None):
    """Clone a new service in the target portal from the definition of an existing service.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    original_feature_service - Existing feature service to clone
    extent - Default extent of the new feature service in WGS84
    folder - The folder to create the service in"""

    try:
        new_item = None
        target = connection['target']

        # Get the definition of the original feature service
        original_item = original_feature_service.item
        fs_url = original_feature_service.url
        request_parameters = {'f' : 'json'}
        fs_json = _solution_helpers.url_request(fs_url, request_parameters, connection['referer'])

        # Create a new service from the definition of the original feature service
        for key in ['layers', 'tables']:
            del fs_json[key]     
        fs_json['name'] = "{0}_{1}".format(original_item.name, str(uuid.uuid4()).replace('-',''))
        url = "{0}sharing/rest/content/users/{1}/".format(connection['url'], connection['username'])
        if folder is not None:
            url += "{0}/".format(folder['id'])
        url += 'createService'
        request_parameters = {'f' : 'json', 'createParameters' : json.dumps(fs_json), 
                              'outputType' : 'featureService', 'token' : connection['token']}
        resp =_solution_helpers.url_request(url, request_parameters, connection['referer'], 'POST')
        new_item = target.content.get(resp['itemId'])        
    
        # Get the layer and table definitions from the original service
        request_parameters = {'f' : 'json'}       
        layers_json = _solution_helpers.url_request(fs_url + '/layers', request_parameters, connection['referer'])

        # Need to remove relationships first and add them back individually 
        # after all layers and tables have been added to the definition
        relationships = {} 
        for table in layers_json['tables']:
            if 'relationships' in table and len(table['relationships']) != 0:
                relationships[table['id']] = table['relationships']
                table['relationships'] = []
     
        for layer in layers_json['layers']:
            if 'relationships' in layer and len(layer['relationships']) != 0:
                relationships[layer['id']] = layer['relationships']
                layer['relationships'] = []

        # Layers needs to come before Tables or it effects the output service
        definition = json.dumps(layers_json, sort_keys=True) 
        new_feature_service = lyr.FeatureService(new_item)
        new_fs_url = new_feature_service.url

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
        item_properties = {}
        for property_name in ITEM_UPDATE_PROPERTIES:
            item_properties[property_name] = original_item[property_name]

        item_properties['tags'].append("source-{0}".format(original_item.id))
        item_properties['tags'] = ','.join(item_properties['tags'])
        item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])
        item_properties['extent'] = extent
        item_properties['text'] = original_item.get_data()

        with tempfile.TemporaryDirectory() as temp_dir:
            thumbnail_file = original_item.download_thumbnail(temp_dir)
            # Updating the metadata changes the tags, leaving out for now.
            #metadata = original_item.download_metadata(temp_dir)     
            new_item.update(item_properties=item_properties, thumbnail=thumbnail_file)
    
        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create service '{0}': {1}".format(original_feature_service.item.title, str(e)), new_item)

def _clone_webmap(connection, original_item, original_item_data, service_mapping, extent, folder=None, group=None):  
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
        target = connection['target']
        
        # Get the item properties from the original web map which will be applied when the new item is created
        item_properties = {}
        for property_name in ITEM_UPDATE_PROPERTIES:
            item_properties[property_name] = original_item[property_name]

        item_properties['name'] = "{0}_{1}".format(original_item['name'], str(uuid.uuid4()).replace('-',''))
        item_properties['tags'].append("source-{0}".format(original_item.id))
        item_properties['tags'] = ','.join(item_properties['tags'])
        item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])
        item_properties['extent'] = extent

        # Swizzle the item ids and URLs of the operational layers and tables in the web map
        webmap_json = original_item_data
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
        item_properties['text'] = json.dumps(webmap_json)
        with tempfile.TemporaryDirectory() as temp_dir: 
            thumbnail_file = original_item.download_thumbnail(temp_dir)
            new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail_file, folder=folder['title'])

        # Share the item with the group if provided
        if group is not None:
            new_item.share(groups=group)

        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create web map '{0}': {1}".format(original_item.title, str(e)), new_item)

def _clone_app(connection, original_item, original_item_data, service_mapping, webmap_mapping, group_mapping, folder=None, group=None):
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
        target = connection['target']

        # Get the item properties from the original application which will be applied when the new item is created
        item_properties = {}
        for property_name in ITEM_UPDATE_PROPERTIES:
            item_properties[property_name] = original_item[property_name]

        item_properties['tags'].append("source-{0}".format(original_item.id))
        item_properties['tags'] = ','.join(item_properties['tags'])
        item_properties['typeKeywords'] = ','.join(item_properties['typeKeywords'])

        # Swizzle the item ids of the web maps, groups and URLs of definied in the application's data
        app_json = original_item_data
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
            thumbnail_file = original_item.download_thumbnail(temp_dir)       
            new_item = target.content.add(item_properties=item_properties, thumbnail=thumbnail_file, folder=folder['title'])

        # Update the url of the item to point to the new portal and new id of the application
        if original_item['url'] is not None:
            find_string = "/apps/"
            index = original_item['url'].find(find_string)
            new_url = '{0}{1}'.format(connection['url'].rstrip('/'), original_item['url'][index:])
            find_string = "id="
            index = new_url.find(find_string)
            new_url = '{0}{1}'.format(new_url[:index + len(find_string)], new_item.id)
            item_properties = {'url' : new_url}
            new_item.update(item_properties)
    
        # Share the item with the group if provided
        if group is not None:
            new_item.share(groups=group)

        return new_item
    except Exception as e:
        raise ItemCreateException("Failed to create application '{0}': {1}".format(original_item.title, str(e)), new_item)

def _get_original_solution_items(source, item, solution_items, group=None):
    """Get the children item and item data of a given item. This is used to recursively find all the items that make up a given map or app.
    Keyword arguments:
    source - The portal containing the item
    item - The item to search
    solution_items - a dictionary that will define the groups, services, maps, and apps that make up a solution
    group - The id of the group to share the web map with"""  
    
    #If the item is an application or dashboard find the web map or group that the application is built from
    if item['type'].lower() in ['web mapping application','operation view']:
        app_json = item.get_data()
        if 'apps' not in solution_items:
            solution_items['apps'] = []
        
        solution_items['apps'].append({'item' : item, 'data' : app_json, 'group' : group })
   
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
                    if 'groups' not in solution_items:
                        solution_items['groups'] = []

                    group_id = app_json['values']['group']
                    solution_items['groups'].append(group_id)
                    search_query = 'group:{0} AND type:{1}'.format(group_id, 'Web Map')
                    items = source.content.search(search_query, max_items=100)
                    for item in items:
                        if item['type'].lower() == 'web map':
                            _get_original_solution_items(source, item, solution_items, group_id)

                if 'webmap' in app_json['values']:
                    webmap_id = app_json['values']['webmap']
        
        if webmap_id is not None:
            webmap = source.content.get(webmap_id)
            _get_original_solution_items(source, webmap, solution_items)

    #If the item is a web map find all the feature service layers and tables that make up the map
    elif item['type'].lower() == 'web map':
        webmap_json = item.get_data()
        if 'maps' not in solution_items:
            solution_items['maps'] = []

        solution_items['maps'].append({'item' : item, 'data' : webmap_json, 'group' : group })

        if 'services' not in solution_items:
            solution_items['services'] = []
        
        if 'operationalLayers' in webmap_json:
            for layer in webmap_json['operationalLayers']:
                if 'layerType' in layer and layer['layerType'] == "ArcGISFeatureLayer":
                    if 'itemId' in layer and layer['itemId'] not in solution_items['services']:
                        solution_items['services'].append(layer['itemId'])

        if 'tables' in webmap_json:
            for table in webmap_json['tables']:
                if 'itemId' in table and table['itemId'] not in solution_items['services']:
                        solution_items['services'].append(table['itemId'])
    
def _get_existing_item(connection, source_id, folder, type):
    """Test if an item with a given source tag already exists in the user's content. 
    This is used to determine if the service, map or app has already been created in the folder.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    source_id - Item id of the original item that is going to be cloned
    folder - The folder to search for the item within
    type - Type of item we are searching for"""  
   
    target = connection['target']
    search_query = 'owner:{0} AND tags:"source-{1}" AND type:{2}'.format(connection['username'], source_id, type)
    items = target.content.search(search_query, max_items=100, outside_org=False)
    for item in items:
        if item['ownerFolder'] == folder['id']:
            return item
    return None 

def _get_existing_group(connection, source_id, folder):
    """Test if a group with a given source tag already exists in the organization. 
    This is used to determine if the group has already been created 
    and if new maps and apps that belong to the same group should be shared to the same group.
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    source_id - Item id of the original folder that is going to be cloned
    folder - The folder that is used as a tag on the group indicating new items created in the same folder should share the group""" 
    
    target = connection['target']
    search_query = 'owner:{0} AND tags:"source-{1},sourcefolder-{2}"'.format(connection['username'], source_id, folder['id']) 
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

def _main(connection, solution, maps_apps, extent, output_folder):
    """Clone a collection of maps and apps into a new portal
    Keyword arguments:
    connection - Dictionary containing connection info to the target portal
    solution - The name of the solution
    maps_apps - A list of maps and apps that have a particular tag to be cloned into the portal
    extent - The default extent of the new maps and services in WGS84
    output_folder - The name of the folder to create the new items within the user's content""" 
    
    source = gis.GIS()
    target = connection['target']
    group_mapping = {}   
    service_mapping = []
    webmap_mapping = {}   
    
    # If the folder does not already exist create a new folder
    folder = {}
    folder_id = target._portal.get_folder_id(connection['username'], output_folder)
    if folder_id is None:
        folder = target.content.create_folder(output_folder)
    else:
        folder = {'title' : output_folder, 'id': folder_id}

    for map_app_name in maps_apps:
        try:
            created_items = []

            # Search for the map or app in the given organization using the map or app name and a specific tag
            search_query = 'accountid:{0} AND tags:"{1},solution.{2}" AND title:"{3}"'.format(_solution_helpers.PORTAL_ID, 'one.click.solution', solution, map_app_name)
            solutions = {}
            items = source.content.search(search_query)
            item = next((item for item in items if item.title == map_app_name), None)
            if item is None:
                continue

            # Check if the item has already been cloned into the target portal and if so, continue on to the next map or app.
            existing_item = _get_existing_item(connection, item.id, folder, item['type'])
            if existing_item is not None:
                _add_message("'{0}' already exists in your {1} folder".format(item.title, folder['title']))
                _add_message('------------------------')
                continue

            # Get the services, groups, maps and apps that make up the solution
            solution_items = {}
            _get_original_solution_items(source, item, solution_items)

            message = 'Deploying {0}'.format(map_app_name)
            _add_message(message) 

            if IS_RUN_FROM_PRO:
                import arcpy
                item_count = len([type for type in solution_items for item in solution_items[type]])
                arcpy.SetProgressor('step', message, 0, item_count, 1)

            # Process and clone the groups that don't already exist
            if 'groups' in solution_items:
                groups = solution_items['groups']
                for original_group_id in groups:
                    if original_group_id in group_mapping: #We have already found or created this item
                        _move_progressor()
                        continue
                
                    original_group = source.groups.get(original_group_id)
                    new_group = _get_existing_group(connection, original_group_id, folder)
                    if new_group is None:
                        new_group = _clone_group(connection, original_group, folder)
                        created_items.append(new_group)
                        _add_message("Created group '{0}'".format(new_group.title))
                    else:
                        _add_message("Existing group '{0}' found".format(new_group.title))
                    group_mapping[original_group.id] = new_group.id
                    _move_progressor()

            # Process and clone the services that don't already exist
            if 'services' in solution_items:
                services = solution_items['services']
                for original_item_id in services:
                    original_item = source.content.get(original_item_id) 
                    if original_item.type != 'Feature Service':
                        continue #TODO, throw error

                    if original_item_id in [service_map[0][0] for service_map in service_mapping]: #We have already found or created this item
                        _move_progressor()
                        continue

                    original_feature_service = lyr.FeatureService(original_item)  
                    new_item = _get_existing_item(connection, original_item_id, folder, 'Feature Service')
                    if new_item is None:                     
                        new_item = _clone_service(connection, original_feature_service, extent, folder)
                        created_items.append(new_item)
                        _add_message("Created service '{0}'".format(new_item.title))   
                    else:
                        _add_message("Existing service '{0}' found in {1}".format(new_item.title, folder['title']))          
                    new_feature_service = lyr.FeatureService(new_item)
                    service_mapping.append([(original_item_id, original_feature_service.url),
                                                (new_item.id, new_feature_service.url)])
                    _move_progressor()

            # Process and clone the maps that don't already exist
            if 'maps' in solution_items:
                for map in solution_items['maps']:
                    original_item = map['item']
                    original_item_data = map['data']

                    if original_item.id in webmap_mapping: #We have already found or created this item
                        _move_progressor()
                        continue
          
                    new_item = _get_existing_item(connection, original_item.id, folder, 'Web Map')
                    if new_item is None:
                        if map['group'] is not None:
                            map['group'] = group_mapping[map['group']]
                        new_item = _clone_webmap(connection, original_item, original_item_data, service_mapping, extent, folder, map['group'])
                        created_items.append(new_item)
                        _add_message("Created map '{0}'".format(new_item.title))
                    else:
                        _add_message("Existing map '{0}' found in {1}".format(new_item.title, folder['title']))  
                    webmap_mapping[original_item.id] =  new_item.id
                    _move_progressor()

            # Process and clone the apps that don't already exist
            if 'apps' in solution_items:
                for app in solution_items['apps']:
                    original_item = app['item']
                    original_item_data = app['data']

                    new_item = _get_existing_item(connection, original_item.id, folder, original_item['type'])
                    if new_item is None:
                        if app['group'] is not None:
                            app['group'] = group_mapping[map['group']]                       
                        new_item = _clone_app(connection, original_item, original_item_data, service_mapping, webmap_mapping, group_mapping, folder, app['group'])
                        created_items.append(new_item)
                        _add_message("Created application '{0}'".format(new_item.title))
                    else:
                        _add_message("Existing application '{0}' found in {1}".format(new_item.title, folder['title'])) 
                    _move_progressor()          

            _add_message('Successfully added {0}'.format(map_app_name))
            _add_message('------------------------')
        except Exception as e:
            if type(e) == ItemCreateException:
                _add_message(e.args[0], 'Error')
                if e.args[1] is not None:
                    created_items.append(e.args[1])
            else:
                _add_message(str(e), 'Error')

            for item in created_items:
                if item.delete():
                    _add_message("Deleted {0}".format(item.title))
            _add_message('Failed to add {0}'.format(map_app_name), 'Error')
            _add_message('------------------------')

def run(portal_url, username, pw, solution, maps_apps, extent, output_folder):
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
    _main(connection, solution, maps_apps, extent, output_folder)

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

    if connection is not None:
        # Get the input parameters
        solution = arcpy.GetParameterAsText(0)
        maps_apps = sorted(list(set(arcpy.GetParameter(1)))) 
        extent = arcpy.GetParameter(2)
        output_folder = arcpy.GetParameterAsText(3)
        arcpy.SetParameterAsText(4, '')

        # Get the default extent of new maps defined in the portal
        if extent is None:
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
        _main(connection, solution, maps_apps, extent_text, output_folder)