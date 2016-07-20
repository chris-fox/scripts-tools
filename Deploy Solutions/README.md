#Steps for setting up your environment to use the tools#
1. Download or Clone this repo
2. Install ArcGIS Pro 1.3
3. Find the application shortcut “Python Command Prompt” that is now available under the ArcGIS program group. Run it as an administrator (You will likely need to run as an administrator, depending on where Pro was installed)
4. Run the following commands from the command prompt:
  `conda install -c conda-forge ipywidgets`
  `conda install -c esri arcgis=0.1`
  This information is documented as well in the [python api install and setup guide](https://developers.arcgis.com/python/guide/Install-and-set-up/)

5.	Extract the contents of arcgis.zip and copy and paste all the contained files to overwrite the contents in the directory below:
C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\lib\site-packages\arcgis
Note: Users will not have to do step 4 when we release, we are just doing this because the beta version has bugs that have since been fixed by the dev team, so this is the latest code.
6.	Extract the contents of tools.zip. Open ArcGIS Pro and browse to the folder you extracted the toolbox and scrips tool to use the tools.

#Using the tools#
##Deploy Solutions##
This tool is used to clone an existing map or app into your organization. The organization or portal that is used as the target to clone the map or app is determined by the active portal in the current session of Pro. You can manage the active portal or sign-in/out of the portal in the upper-right corner of the application:

The tool looks for items (maps or apps) in the state & local try it live org with specific tags to determine what items can be cloned (We can modify this logic later as needed). To use the tool:


1. Ensure you are logged into the portal you wish to create the content in
2. Select the name of the solution containing the maps and apps you wish to create
3. Select one or more map and apps
4. Specify the default output extent of the maps and apps
  a. Default will use the default extent defined in the target portal
  b. Alternatively select the extent of the current extent in the map, layer, or dataset
5. Specify the output folder to create the new items in. You can also type a new folder name to create a new folder for the items.
Note: The folder is critical in this workflow as it is used to organize maps and apps that share services as part of a larger workflow. This allows the tool to know if a service has already been created if it finds one already in the folder.
6.	Run the tool
The tool should create all the services, groups, maps and apps needed for the selected solution. By default, everything remains private, unless shared with a group for group web application.
How to add your own maps/apps to the tool
This tool is only designed to work on solutions that are entirely hosted, ie the services, maps and apps are all hosted by the portal. The tool looks for maps and apps in the state & local try it live org, http://statelocaltryit.maps.arcgis.com/ that contain specific tags. We can modify this in the future as we settle on which org will host this content. To add a map or app to the tool from this org do the following:

1.	Browse to the item in the org, the map or app.
2.	Add the following tags to the item:
a.	one.click.solution
b.	solution.SolutionName (Replace SolutionName with the name of the solution associated with the map or app. This is what is displayed in the first parameter of the tool. This is good when organizing a collection of maps and apps that work together, such as Manage Mosquito Populations which is composed of many maps and apps.)
Note: Only add these tags to final component of the solution. For example, if it is geoform application, just add the tag to the item associated with the geoform app. You don’t need to add the tags to the map or services that make up the app. If it is a collector map, just add the tags to the item for the collector map, etc.
3.	Open the tool, it should search the organization for the items with the tags and add them to the dropdowns in the parameters.

Known-Issues
1.	Failed to create service 'ExistingAddresses': {'error': {'code': 400, 'message': 'Unable to add feature service definition.', 'details': ["Column 'Shape' in table 'user_2461.ExistingAddresses_70fa36a3353641aeb9af86b49a6ec605_SITE_ADDRESS_POINTS' is of a type that is invalid for use as a key column in an index or statistics."]}}

If you receive an error like the one above this is due to a bug that occurs when the original service was published from ArcGIS 10.4 and Pro 1.2. The service contains some invalid index definitions and if you attempted to clone this service in arcgis.com it would also fail. Below are the steps to resolve this which require modifying the definition of the original service. If you are not comfortable with going through these steps, I can help out to get the service cleaned up.

1. Go to the rest end point for the feature service sub layer (you would need to repeat this for every layer in the service)
2. In the url add ‘admin’ between ‘rest’ and ‘services’ (ie rest/admin/services) and hit enter
3. Scroll to the bottom and click the link “delete from definition”
4. Search in the delete from layer definition dialog for ‘indexes’ and examine the current indexes looking for duplicate indexes, or indexes with name of FDO_OBJECTID or FDO_SHAPE.
5. Select all the text in the delete from layer definition dialog and use the JSON example below to delete these duplicate indexes from the layer
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
6. Click Delete from Layer Definition

2.	The services used by the web map are not created.
This can happen depending on how the layers were added to the webmap. If the layer was added by opening a feature service item in a new web map, or by searching for a layer than everything should be fine. The problem occurs if a layer was added to the map via a URL to the service. Layers added this way don’t have an item id associated with them so I am not currently picking these up as items to clone.
I am interested to see how many maps this effects and then we can decide the best way to resolve this. It is a pretty easy fix to the webmap json if it isn’t many maps.

Update Domains
This tool is used to add, remove, or update the domain for a field in a hosted feature service. 

To use the tool:
1.	Ensure you are logged into the portal as the owner of the hosted feature service you want to modify
2.	Browse to the feature service you wish to modify or select it from the dropdown if it is in the map
3.	Select the field that has the domain you wish to modify
4.	If the field already has a domain, it will populate all the remaining parameters with the information about the domain.
a.	To modify an existing coded value domain:
i.	Change any code or value
ii.	Add a new code/value pair
iii.	Remove an existing code/value by clicking the row and clicking the red ‘x’ at the beginning of the row
b.	To modify an existing range domain:
i.	Change the min/max value
c.	To add a new domain to a field:
i.	Select the domain type
ii.	Give the domain a name
iii.	Input the codes/values or min/max for the domain
d.	To remove a domain for a field:
e.	Select ‘None’ for Type
5.	Run the tool

Add/Remove Field
These tools are the out of the box GP tools. They already work on Hosted Feature services so no custom code for these workflows was necessary.
