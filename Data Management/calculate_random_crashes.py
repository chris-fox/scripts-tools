import arcpy, os, sys, random

input_roads = r'F:\Solutions\Tasks\May2016\CrashAnalysis\LocalGovernment\BasicSegmentationOutput.gdb\Segments'
crashes = r'F:\Solutions\Tasks\May2016\CrashAnalysis\LocalGovernment\crashanalysisdata.gdb\CrashLocations'

crashes_per_year = 3208 #Total Crashes
#crashes_per_year = 671 #Total Injury Crashes
#crashes_per_year = 110 #Total Injury A Crashes
years = ['2011', '2012', '2013']

weighted_segments = []
segment_lookup = {}

search_fields = ["OID@", "SHAPE@", "USRAP_AVG_AADT", "SHAPE@LENGTH", "ROUTE_NAME"]
with arcpy.da.SearchCursor(input_roads, search_fields) as cursor:
    for row in cursor:
        segment_lookup[row[0]] = (row[1], row[4])
        weighted_segments.extend([row[0]] * int((row[2] / 100) * row[3]))

max = len(weighted_segments) - 1

insert_fields = ["SHAPE@", "CRASH_YEAR", "ROUTE_NAME"]
with arcpy.da.InsertCursor(crashes, insert_fields) as cursor:
    for year in years:
        for i in range(0, crashes_per_year):
            segment = segment_lookup[weighted_segments[random.randint(0, max)]]
            geom = segment[0].positionAlongLine(random.uniform(0, 1), True)
            row = (geom, year, segment[1])
            cursor.insertRow(row)

