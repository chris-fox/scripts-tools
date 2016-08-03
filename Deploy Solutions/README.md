#Steps for setting up your environment to use the tools#
1. Download or Clone this repo
2. Install ArcGIS Pro 1.3
3. Find the application shortcut “Python Command Prompt” that is now available under the ArcGIS program group. (You will likely need to run as an administrator if Pro was installed with the default settings)
4. Run the following commands. This information is documented as well in the [python api install and setup guide](https://developers.arcgis.com/python/guide/Install-and-set-up/)
   
    ```
    conda install -c conda-forge ipywidgets
    ```
    ```
    conda install -c esri arcgis=0.1
    ```
5. Go to https://github.com/ArcGIS/geosaurus and download or clone the repo
6. Copy the contents of /src/arcgis and overwrite the contents of the arcgis package in your Pro 1.3 install location. By default this location would be C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\lib\site-packages\arcgis
    - Note: Users will not have to do step 5 and 6 when we release, we are just doing this because the beta version has bugs that have since been fixed so we want to use latest code.
7. In ArcGIS Pro browse to the Solutions.tbx you downloaded from this repo and start using the tools

#Using the tools#
##Deploy Solutions Tool##
This tool is used to clone an existing map or app into your organization. The organization or portal that is used as the target to clone the map or app is determined by the active portal in the current session of Pro. You can manage the active portal or sign-in/out of the portal in the upper-right corner of the application. To use the tool:

1. Ensure you are logged into the portal you wish to create the content in
2. Select the name of the solution containing the maps and apps you wish to create
3. Select one or more of the map and apps
4. Specify the output extent of the maps and apps
    - Default will use the default extent defined in the target portal
    - Alternatively select the extent of the current extent in the map, layer, or dataset
5. Specify the output folder to create the new items in. You can also type a new folder name to create a new folder for the items.
    - Note: The folder is critical in this workflow as it is used to organize maps and apps that share services as part of a larger workflow. This allows the tool to know if a service has already been created if it finds one already in the folder.
6. Run the tool

The tool should create all the services, groups, maps and apps needed for the selected solution.

###How to add your own maps/apps to the tool###

This tool is only designed to work on solutions that are entirely hosted, ie the services, maps and apps are all hosted by the portal. The tool by default looks for maps and apps in the [state & local try it live org](http://statelocaltryit.maps.arcgis.com/) that contain specific tags.

To modify which org to search for items with the specified tags, change the value of the PORTAL_ID variable in the Deploy Solution.pyt file to the ID of the organization that contains the items.

To add aditional maps and apps to the tool:

1. Browse to the item in the org and add the following tags to the item:
    - one.click.solution
    - solution.*SolutionName* (Replace *SolutionName* with the name of the solution associated with the map or app. This is what is displayed in the first parameter of the tool. This is good when organizing a collection of maps and apps that work together, such as Manage Mosquito Populations which is composed of many maps and apps.)

    Note: Only add these tags to final component of the solution. For example, if it is geoform application, just add the tag to the item associated with the geoform app. You don’t need to add the tags to the map or services that make up the app. If it is a collector map, just add the tags to the item for the collector map, etc.
2. Open the tool, it should search the organization for the items with the tags and add them to the dropdowns in the parameters.

###Known-Issues###
####Failed to create service####
*'ExistingAddresses': {'error': {'code': 400, 'message': 'Unable to add feature service definition.', 'details': ["Column 'Shape' in table 'user_2461.ExistingAddresses_70fa36a3353641aeb9af86b49a6ec605_SITE_ADDRESS_POINTS' is of a type that is invalid for use as a key column in an index or statistics."]}}*

If you receive an error like the one above this is due to a bug that occurs when the original service was published from ArcGIS 10.4 and Pro 1.2. The service contains some invalid index definitions and if you attempted to clone this service in arcgis.com it would also fail. Below are the steps to resolve this which require modifying the definition of the original service. If you are not comfortable with going through these steps, I can help out to get the service cleaned up.

1. Go to the rest end point for the feature service sub layer (you would need to repeat this for every layer in the service)
2. In the url add ‘admin’ between ‘rest’ and ‘services’ (ie rest/admin/services) and hit enter
3. Scroll to the bottom and click the link “delete from definition”
4. Search in the delete from layer definition dialog for ‘indexes’ and examine the current indexes looking for duplicate indexes, or indexes with name of FDO_OBJECTID or FDO_SHAPE.
5. Clear out all the text in the delete from layer definition dialog and use the JSON example below to delete duplicate indexes from the service

    ```
    {
      "indexes" : [
      {
        "name" : "FDO_OBJECTID"
      },
      {
        "name" : "FDO_SHAPE" 
      }
    ]
    }
    ```
6. Click Delete from Layer Definition

####Tool completes succesfully but no services created####
This can happen depending on how the layers were added to the webmap. If the layer was added by opening a feature service item in a new web map, or by searching for a layer and adding it than everything should be fine. The problem occurs if a layer was added to the map via a URL to the service. Layers added this way don’t have an item id associated with them so I am not currently picking these up as items to clone.

I am interested to see how many maps this effects and then we can decide the best way to resolve this. It is a pretty easy fix to the webmap json if it isn’t many maps.

##Update Domains Tool##

This tool is used to add, remove, or update the domain for a field in a hosted feature service. To use the tool:

1. Ensure you are logged into the portal as the owner of the hosted feature service you want to modify
2. Browse to the feature service you wish to modify or select it from the dropdown if it is in the map
3. Select the field that has the domain you wish to modify
4. If the field already has a domain, it will populate all the remaining parameters with the information about the domain.
    - To modify an existing coded value domain
        1. Change any code or value
        2. Add a new code/value pair
        3. Remove an existing code/value by selecting the row and clicking the red ‘x’ at the beginning of the row
    - To modify an existing range domain, change the min/max value
    - To add a new domain to a field
        1. Select the domain type
        2. Give the domain a name
        3. Input the codes/values or min/max for the domain
    - To remove a domain for a field, select ‘None’ for Type
5. Run the tool

##Alter Field Alias Tool##

This tool is used to add, remove, or update the domain for a field in a hosted feature service. To use the tool:

1. Ensure you are logged into the portal as the owner of the hosted feature service you want to modify
2. Browse to the feature service you wish to modify or select it from the dropdown if it is in the map
3. Select the field that has the domain you wish to modify
4. Change the alias of the field
5. Run the tool

##Add/Remove Field Tools##

These tools are the out of the box GP tools. They already work on Hosted Feature services so no custom code for these workflows was necessary.
