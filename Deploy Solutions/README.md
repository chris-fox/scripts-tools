#Steps for setting up your environment to use the tools#
1. [Download](https://github.com/chris-fox/scripts-tools/archive/master.zip) or Clone this repo
2. Install ArcGIS Pro 1.3
3. Find the application shortcut “Python Command Prompt” that is now available under the ArcGIS program group. Run it as an administrator.
4. Run the following command.
   
    ```
    conda install arcgis
    ```
5. In ArcGIS Pro browse to the Deploy Solutions.pyt you downloaded from this repo and start using the tools

#Using the tools#
##Clone Items##
This tools is used to clone publically available items in arcgis online into your organization. The organization or portal that is used as the target to clone the map or app is determined by the active portal in the current session of Pro. You can manage the active portal or sign-in/out of the portal in the upper-right corner of the application. To use the tool:

1. Ensure you are logged into the portal you wish to create the content in
2. Enter the item id of the item you want to clone. Once you click out of the parameter a new row will be added and you can add additional item ids. If you are cloning a map or an app, you don't need to provide the id of the services or groups. They will automatically be cloned as well.
3. Specify whether the data from any feature services should also be copied to the cloned feature service. 
4. Specify the output folder to create the new items in. You can also type a new folder name to create a new folder for the items.
    - Note: The folder is critical in this workflow as it is used to organize maps and apps that share services as part of a larger workflow. This allows the tool to know if a service has already been created if it finds one already in the folder.
5. Specify the output extent of the maps and apps
    - Default will use the default extent defined in the target portal
    - Alternatively select the extent of the current extent in the map, layer, or dataset
6. Run the tool

In addition, provided in the repo is a sample script, example.py, that shows how you can clone items through code. This could be useful in automating this process or if you need clone items that are not shared with everyone. The comments in the sample script show how to specify the source and target portals for cloning.

##Deploy Solutions Tool##
This tool is used to clone an existing map or app into your organization. The organization or portal that is used as the target to clone the map or app is determined by the active portal in the current session of Pro. You can manage the active portal or sign-in/out of the portal in the upper-right corner of the application. To use the tool:

1. Ensure you are logged into the portal you wish to create the content in
2. Select the name of the industry
2. Select the group of solutions you are interested in
3. Select one or more of the solutions
4. Specify whether the data from any feature services should also be copied to the cloned feature service. 
5. Specify the output folder to create the new items in. You can also type a new folder name to create a new folder for the items.
    - Note: The folder is critical in this workflow as it is used to organize maps and apps that share services as part of a larger workflow. This allows the tool to know if a service has already been created if it finds one already in the folder.
6. Specify the output extent of the maps and apps
    - Default will use the default extent defined in the target portal
    - Alternatively select the extent of the current extent in the map, layer, or dataset
7. Run the tool

The tool should create all the services, groups, maps and apps needed for the selected solution.

###How to add your own maps/apps to the tool###

This tool is only designed to work on solutions that are entirely hosted, ie the services, maps and apps are all hosted by the portal. The tool by default looks for maps and apps in the [solutions deployment org](#http://arcgissolutionsdeploymentdev.maps.arcgis.com/) that are shared with specific groups and contain specific tags.

To add aditional maps and apps to the tool:

1. Browse to the item in this deployment org and do the following. 
    - Share the item with the industry group that the solution falls under, for example ArcGIS for Local Government. If the group for the industry doesn't already exist you can create a new group in the organization. The name of the group is what will show up in the list under the first parameter of the tool. Add the tag 'one.click.solution' to the group to signify that the group contains items that can be deployed with this Deploy Solutions Tool.
    - Add the tag solution.*SolutionGroup* to the item (Replace *SolutionGroup* with the name of the group associated with the solution. This is what is displayed in the second parameter of the tool. This is good when organizing a collection of maps and apps that work together, such as Manage Mosquito Populations which is composed of many maps and apps.). You can repeat this tag with different group names if the solution item should appear under multiple groups.

    Note: Only share the item and add tags to final component of the solution. For example, if it is geoform application, just share and add the tag to the item associated with the geoform app. You don’t need to add the tags to the map or services that make up the app. If it is a collector map, just add the tags to the item for the collector map, etc.
    
2. Share the item and all the service, groups and maps associated with everyone. They need to be publically available to be seen by the tool.
3. Open the tool, it should search the organization for the items with the tags and add them to the dropdowns in the parameters.

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

##Open Web Map Tool##

This tool to open the web map viewer for the specified web map. To use the tool:

1. Ensure you are logged into the portal containing the web map you want to work with.
2. Select the folder in your content containing the web map
3. Select the web map
4. Run the tool
