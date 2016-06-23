import arcpy, os

ID_LOOKUP_TABLE = "GDB_ServiceItems"
TABLE_ID_FIELD = "ItemId"
TABLE_DATASET_FIELD = "DatasetName"

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Update Datasources"
        self.alias = "update"

        # List of tool classes associated with this toolbox
        self.tools = []
        if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
            self.tools = [ArcMapUpdateDatasource]
        elif arcpy.GetInstallInfo()['ProductName'] == 'ArcGISPro':
            self.tools = [ProUpdateDatasource]   

class ArcMapUpdateDatasource(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Update Datasource"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(
            displayName="Feature Service Layers and Tables",
            name="in_tables",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param1 = arcpy.Parameter(
            displayName="New Datasource",
            name="datasource",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
            multiValue=False)
        param1.filter.list = ["Local Database"]

        return [param0, param1]

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return arcpy.GetInstallInfo()['ProductName'] == 'Desktop'

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if not parameters[0].hasBeenValidated:
            mxd = arcpy.mapping.MapDocument('Current')
            map_members = [l.name for l in arcpy.mapping.ListLayers(mxd) if hasattr(l, 'datasetName') and l.datasetName.isnumeric()]
            map_members.extend([t.name for t in arcpy.mapping.ListTableViews(mxd) if hasattr(t, 'datasetName') and  t.datasetName.isnumeric()])
            parameters[0].filter.list = map_members

        if parameters[1].altered:
            _validate_gdb(parameters[1])
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        map_members = parameters[0].value
        gdb = parameters[1].valueAsText

        id_dataset_mapping = _get_id_mapping(gdb)

        mxd = arcpy.mapping.MapDocument('Current')
        layers = [l for l in arcpy.mapping.ListLayers(mxd) if hasattr(l, 'datasetName') and l.datasetName.isnumeric()]
        tables = [t for t in arcpy.mapping.ListTableViews(mxd) if hasattr(t, 'datasetName') and t.datasetName.isnumeric()]
        
        messages.addMessage(arcpy.env.workspace)

        for i in range(0, map_members.rowCount):
            map_member_name = map_members.getValue(i, 0)
            map_member = next((l for l in layers if l.name == map_member_name), None)
            if map_member is None:
                map_member =  next((t for t in tables if t.name == map_member_name), None)

            id = map_member.datasetName
            if id not in id_dataset_mapping:
                messages.addWarningMessage("Feature Service layer id: {0} not found in the lookup table '{1}', unable to update source for {2}".format(id, ID_LOOKUP_TABLE, map_member.name))
                continue

            dataset = id_dataset_mapping[id]
            if not arcpy.Exists(os.path.join(gdb, dataset)):
                messages.addWarningMessage("Dataset: {0} not found in the geodatabase, unable to update source for {1}".format(dataset, map_member.name))
                continue

            map_member.replaceDataSource(gdb, "FILEGDB_WORKSPACE", dataset)
        return

class ProUpdateDatasource(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Update Datasource"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(
            displayName="Map",
            name="map",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=False)

        param1 = arcpy.Parameter(
            displayName="Feature Service Layers and Tables",
            name="in_tables",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param2 = arcpy.Parameter(
            displayName="New Datasource",
            name="datasource",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
            multiValue=False)
        param2.filter.list = ["Local Database"]

        return [param0, param1, param2]

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return arcpy.GetInstallInfo()['ProductName'] == 'ArcGISPro'

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        prj = arcpy.mp.ArcGISProject('Current')
        parameters[0].filter.list = [m.name for m in prj.listMaps()]

        if (parameters[0].altered):
            prj = arcpy.mp.ArcGISProject('Current')
            map = next((m for m in prj.listMaps() if m.name == parameters[0].value), None)
            if map is not None:
                map_members = [l.name for l in map.listLayers() if l.connectionProperties is not None and l.connectionProperties['workspace_factory'] == 'FeatureService']
                map_members.extend([t.name for t in map.listTables() if t.connectionProperties is not None and t.connectionProperties['workspace_factory'] == 'FeatureService'])
                parameters[1].filter.list = map_members            
        else:
            parameters[1].filter.list = []
            parameters[1].value = ""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if parameters[0].altered:
            if len(parameters[1].filter.list) == 0:
                parameters[0].setErrorMessage("Map contains no feature service layers or tables")
            else:
                parameters[0].clearMessage()

        if parameters[2].altered:
            _validate_gdb(parameters[2])
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        map = parameters[0]
        map_members = parameters[1].value
        gdb = parameters[2].valueAsText

        id_dataset_mapping = _get_id_mapping(gdb)

        prj = arcpy.mp.ArcGISProject('Current')
        map = next((m for m in prj.listMaps() if m.name == parameters[0].value), None)
        layers = [l for l in map.listLayers() if l.isWebLayer and l.isFeatureLayer]
        tables = [t for t in map.listTables() if t.connectionProperties['workspace_factory'] == 'FeatureService']
        
        for i in range(0, map_members.rowCount):
            map_member_name = map_members.getValue(i, 0)
            map_member = next((l for l in layers if l.name == map_member_name), None)
            if map_member is None:
                map_member =  next((t for t in tables if t.name == map_member_name), None)

            connection_properties = map_member.connectionProperties
            id = connection_properties['dataset']
            if id not in id_dataset_mapping:
                messages.addWarningMessage("Feature Service layer id: {0} not found in the lookup table '{1}', unable to update source for {2}".format(id, ID_LOOKUP_TABLE, map_member.name))
                continue

            dataset = id_dataset_mapping[id]
            if not arcpy.Exists(os.path.join(gdb, dataset)):
                messages.addWarningMessage("Dataset: {0} not found in the geodatabase, unable to update source for {1}".format(dataset, map_member.name))
                continue

            new_connection_properties = {'dataset':dataset, 'workspace_factory':'File Geodatabase', 'connection_info' : {'database': gdb}}
            map_member.updateConnectionProperties(connection_properties, new_connection_properties)
        return

def _validate_gdb(param):
    arcpy.env.workspace = param.valueAsText
    if arcpy.Exists(ID_LOOKUP_TABLE):
        fields = [f.name for f in arcpy.ListFields(ID_LOOKUP_TABLE)]
        if fields.count(TABLE_ID_FIELD) > 0 and fields.count(TABLE_DATASET_FIELD) > 0:
            param.clearMessage()
            return
          
    param.setErrorMessage("GDB must contain a lookup table '{0}' containing two fields ('{1} and '{2}') which maps the feature service layer id to the corresponding dataset name".format(ID_LOOKUP_TABLE, TABLE_ID_FIELD, TABLE_DATASET_FIELD))

def _get_id_mapping(gdb):
    arcpy.env.workspace = gdb
    id_dataset_mapping = {}
    with arcpy.da.SearchCursor(ID_LOOKUP_TABLE, [TABLE_ID_FIELD, TABLE_DATASET_FIELD]) as rows:
        for row in rows:
            id_dataset_mapping[str(row[0])] = row[1]
    del rows, row
    return id_dataset_mapping
