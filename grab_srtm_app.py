import geopandas as gpd
import requests
import streamlit as st
import pydeck as pdk
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from osgeo import gdal
from shapely.geometry import Polygon
from fiona.drvsupport import supported_drivers

st.set_page_config(layout="wide")

st.title('SRTM Extraction Tool')

st.sidebar.image('./logo.png', width = 260)
st.sidebar.markdown('#')
st.sidebar.write('This application extracts SRTM data for a given KML or manually inputted bounding box.')
st.sidebar.write('The output SRTM file is in WGS 84 UTM and is ready for import to WingtraHub.')
st.sidebar.write('If you have any questions regarding the application, please contact us at support@wingtra.com.')
st.sidebar.markdown('#')
st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')

# Read KML

def convert2poly(multi):
    if type(multi) != Polygon:
        poly = list(multi.geoms)[0]
    else:
        poly = multi
    return poly

defined = False
option = st.selectbox(
    'Select method for defining the bounds:',
    ('<Method>', 'KML Upload', 'Manual Input'))

if option == 'Method':
    st.stop()

elif option == 'KML Upload':
    uploaded = False
    kml_upload = st.file_uploader('Please Select KML boundary.', accept_multiple_files=False)
    if kml_upload is not None:
        if kml_upload.name.lower().endswith('.kml'):
            uploaded = True
        else:
            msg = 'Please upload a KML file.'
            st.error(msg)
            st.stop()
    
    if uploaded:

        fname = kml_upload.name
        supported_drivers['KML'] = 'rw'
        input_kml = gpd.read_file(kml_upload, driver='KML')
        multi_poly = list(input_kml['geometry'])
        xx = []
        yy = []
        
        if len(multi_poly) == 1:
            if type(multi_poly[0]) == Polygon:
                poly = multi_poly[0]
            else:
                poly = convert2poly(multi_poly[0])
            xs, ys = poly.exterior.coords.xy
            for x in xs:
                xx.append(x)
            for y in ys:
                yy.append(y)          
        else:
            polys = list(map(convert2poly,multi_poly))       
            for poly in polys:
                xs, ys = poly.exterior.coords.xy
                for x in xs:
                    xx.append(x)
                for y in ys:
                    yy.append(y)
        
        east = max(xx) + 0.01
        west = min(xx) - 0.01
        north = max(yy) + 0.01
        south = min(yy) - 0.01
        defined = True
            
elif option == 'Manual Input':
    st.subheader('Please define the bounding box.')
    st.text('Input the coordinates from conrer 1 to 4 where corner 1 is the upper-left corner moving clockwise.')
    col1, col2 = st.columns(2)
    
    with col1:
        cor1_lat = st.text_input('Input Corner 1 Latitude:')
        cor2_lat = st.text_input('Input Corner 2 Latitude:')
        cor3_lat = st.text_input('Input Corner 3 Latitude:')
        cor4_lat = st.text_input('Input Corner 4 Latitude:')
    with col2:        
        cor1_lon = st.text_input('Input Corner 1 Longitude:')        
        cor2_lon = st.text_input('Input Corner 2 Longitude:')        
        cor3_lon = st.text_input('Input Corner 3 Longitude:')        
        cor4_lon = st.text_input('Input Corner 4 Longitude:')
    
    lon_test = cor1_lon != '' and cor2_lon != '' and cor3_lon != '' and cor4_lon != ''
    lat_test = cor1_lat != '' and cor2_lat != '' and cor3_lat != '' and cor4_lat != ''
    
    if lon_test and lat_test:
        lon = [float(cor1_lon), float(cor2_lon), float(cor3_lon), float(cor4_lon)]
        lat = [float(cor1_lat), float(cor2_lat), float(cor3_lat), float(cor4_lat)]
        
        pairs = [(lon[0],lat[0]), (lon[1],lat[1]), (lon[2],lat[2]), (lon[3], lat[3])]
        set_pairs = set(pairs)
        unique = len(set_pairs)
        
        if unique != len(pairs):
            msg = 'No two coordinates can be equal. Please reconsider input.'
            st.error(msg)
            st.stop()
    else:
        st.stop()
    
    fname = 'raster'
    east = max(lon) + 0.01
    west = min(lon) - 0.01
    north = max(lat) + 0.01
    south = min(lat) - 0.01
    defined = True

else:
    st.stop()

# Visualize Bounding Box
if defined:
    if st.button('Visualize Bounds and Extract Data'):
        box = [[[east, north], [west, north], [west, south], [east, south]]]
        
        view = pdk.data_utils.viewport_helpers.compute_view(box[0], view_proportion=1)
        level = int(str(view).split('"zoom": ')[-1].split('}')[0])
        
        INITIAL_VIEW_STATE = pdk.ViewState(latitude=(north+south)/2, 
                                           longitude=(east+west)/2,
                                           zoom=level,
                                           pitch=0)
        
        polygon = pdk.Layer("PolygonLayer",
                            box,
                            get_polygon='-',
                            get_fill_color=[39, 157, 245],
                            get_line_color=[0, 0, 0],
                            opacity=0.2,
                            )
        
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/satellite-streets-v11',
            initial_view_state=INITIAL_VIEW_STATE,
            layers=[polygon]
            ))   
    
        # Retrieve SRTM data
        with st.spinner('Extracting SRTM data...'):
            api_key = '9650231c82589578832a8851f1692a2e'
            req = 'https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south=' + str(south) + '&north=' + str(north) + '&west=' + str(west) + '&east=' + str(east) + '&outputFormat=GTiff&API_Key=' + api_key
            
            resp = requests.get(req)
            name = fname.split('.')[0]
            raster_name = name+'_srtm.tif'
            open(raster_name, 'wb').write(resp.content)
            
            # Convert to UTM
            utm_crs_list = query_utm_crs_info(
                datum_name="WGS 84",
                area_of_interest=AreaOfInterest(
                    west_lon_degree=west,
                    south_lat_degree=south,
                    east_lon_degree=east,
                    north_lat_degree=north,
                ),
            )
            
            utm_crs = 'EPSG:'+str(CRS.from_epsg(utm_crs_list[0].code).to_epsg())
            output = 'custom_elev_'+raster_name
            kwargs = {'format': 'GTiff', "srcSRS":"EPSG:4326", "dstSRS":utm_crs, "xRes":"30", "yRes":"30"}
            
            gdal.Warp(output, raster_name, **kwargs)
    
        with open(output, 'rb') as f:
            st.download_button('DOWNLOAD SRTM DATA', f, file_name=output)
    else:
        st.stop()

else:
    st.stop()
