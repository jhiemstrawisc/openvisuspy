import sys

# //////////////////////////////////////////////////////////////////////////////////////
if __name__.startswith('bokeh'):

	from openvisuspy import SetupLogger, IsPanelServe, GetBackend, Slices
	from openvisuspy.probes import ProbeTool

	logger = SetupLogger()
	logger.info(f"GetBackend()={GetBackend()}")

	is_panel = IsPanelServe()
	if is_panel:
		import panel as pn

		doc = None
	else:
		import bokeh

		doc = bokeh.io.curdoc()
		doc.theme = 'light_minimal'

	if False:
		view = Slice(doc=doc, is_panel=is_panel, )
		view.setShowOptions(
			["datasets", "direction", "offset", "palette", "field", "resolution", "num_refinements", "colormapper_type",
			 "palette_range_mode", "palette_range_vmin", "palette_range_vmax"])
	else:
		view = Slices(doc=doc, is_panel=is_panel, cls=ProbeTool)
		view.setShowOptions([
			["datasets", "palette", "view_dep", "resolution", "num_refinements", "colormapper_type", "show_metadata",
			 "logout"],
			["datasets", "direction", "offset", "colormapper_type", "palette_range_mode", "palette_range_vmin",
			 "palette_range_vmax", "show-probe"]
		])

	view.setDataset(sys.argv[1])

	if is_panel:
		main_layout = view.getMainLayout()
		use_template = True
		if use_template:
			template = pn.template.MaterialTemplate(title='NSDF Dashboard')
			template.main.append(main_layout)
			template.servable()
		else:
			main_layout.servable()
	else:

		main_layout = view.getMainLayout()
		doc.add_root(main_layout)
