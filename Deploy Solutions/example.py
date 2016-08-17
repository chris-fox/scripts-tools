import imp, os
from arcgis import gis

if __name__ == "__main__":
    # Import the python toolbox as a module called 'deploy_solutions'
    python_toolbox = os.path.join(os.path.dirname(__file__), 'Deploy Solutions.pyt')
    deploy_solutions = imp.load_source('deploy_solutions', python_toolbox)

    # Specify the source portal, the organization that the items to clone will be searched for
    # If the item to be cloned is shared with everyone and is on arcgis online you don't need to change anything below.
    # if the item is on a local portal or not shared you need to provide the url to the portal and the username and password. 
    source = gis.GIS()

    # Specify the target portal, provide the url and the username/password to the organization or portal you want to clone the items to.
    # Provide the url to the organization rather than just www.arcgis.com, for example 'http://arcgis4localgov2.maps.arcgis.com/'
    target = gis.GIS('http://www.arcgis.com', 'username', 'password')

    # Provide the list of item's ids to clone. 
    # If it is an application or map, you don't need to provide the item id's of the services used by the map or the map used by the application.These items will automatically be cloned as well
    item_ids = ['3bae76bdbf72478a84eae2dbbfd0fd40', 'e69ea3857d424af2bb62145c30c5c714']
    
    for id in item_ids:
        item = source.content.get(id)

        print('Cloning {0}'.format(item['title']))
            
        # Specify the name of the folder to clone the items to. If it doesn't already exist it will be created.
        folder_name = "Test"

        # Optionally provide an arcpy.Extent to set the output extent of the cloned items.
        extent = None

        # Optionally specify whether the data from the original feature service should be copied to the cloned service.
        copy_data = False

        deploy_solutions.clone_item(target, item, folder_name, extent, copy_data)




