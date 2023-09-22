import os,sys,logging,base64,json,types
import requests
from requests.auth import HTTPBasicAuth

# //////////////////////////////////////////////////////////////////////////////////////
if __name__.startswith('bokeh'):

	from openvisuspy import SetupLogger,IsPanelServe,GetBackend,Slice, Slices,cbool
	from openvisuspy.probes import ProbeTool
	
	logger=SetupLogger()
	logger.info(f"GetBackend()={GetBackend()}")

	probe=True
	cls=ProbeTool if probe else Slice

	if False:
		view=cls(show_options=[
			"datasets", "direction", "offset", "palette",  "field", "quality", "num_refinements", "colormapper_type","palette_range_mode","palette_range_vmin","palette_range_vmax"
		])
	else:
		view=Slices(
			show_options=["datasets", "num_views", "palette", 
								 #"field", 
								 "quality", "num_refinements", "colormapper_type","show_metadata"],  
			slice_show_options=["datasets", "direction", "offset", "colormapper_type", "palette_range_mode","palette_range_vmin","palette_range_vmax"],
			cls=cls
		)
		import bokeh.io
		bokeh.io.curdoc().theme = 'light_minimal'

	# can load the config file from remote
	url=sys.argv[1]
	if ".json" in url:

		config_filename=sys.argv[1]
		if config_filename.startswith("http"):
			username=os.environ.get("MODVISUS_USERNAME","")
			password=os.environ.get("MODVISUS_PASSWORD","")
			if username and password:
				auth=HTTPBasicAuth(username,password) if username else None
			else:
				auth=None
			response = requests.get(config_filename,auth = auth)
			config=response.json()
		else:
			config=json.load(open(sys.argv[1],"r"))

		# print(json.dumps(config,indent=2))
		view.setConfig(config)
	else:
		view.setDataset(url)
	
	central=view

	if IsPanelServe():
		from openvisuspy.utils import GetPanelApp
		main_layout=central.getPanelLayout()
		app=GetPanelApp(main_layout)
		app.servable()
	else:
		import bokeh
		doc=bokeh.io.curdoc()
		main_layout=central.getBokehLayout(doc=doc)
		doc.add_root(main_layout)

	

