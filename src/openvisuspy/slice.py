import base64
import types
import logging
import copy
import traceback
import io 
import threading
import time
from urllib.parse import urlparse, urlencode

import numpy as np

from .utils   import *
from .backend import Aborted,LoadDataset,ExecuteBoxQuery,QueryNode

from .canvas import Canvas 

logger = logging.getLogger(__name__)

import bokeh
from bokeh.models.scales import LinearScale,LogScale
from bokeh.models import LinearColorMapper,LogColorMapper,ColorBar,ColumnDataSource,Range1d
from bokeh.models.formatters import NumeralTickFormatter

import param 

import panel as pn
from panel.layout import FloatPanel
from panel import Column,Row,GridBox,Card
from panel.pane import HTML,JSON,Bokeh

SLICE_ID=0
EPSILON = 0.001

DEFAULT_SHOW_OPTIONS={
	"top": [
		["open_button","save_button","info_button","copy_url_button", "logout_button", "scene", "timestep", "timestep_delta", "palette",  "color_mapper_type", "resolution", "view_dependent", "num_refinements"],
		["field","direction", "offset", "range_mode", "range_min",  "range_max"]
	],
	"bottom": [
		["request","response"]
	]
}

# ////////////////////////////////////////////////////////////////////////////////////
class Slice(param.Parameterized):

	render_id              = pn.widgets.IntSlider(name="RenderId", value=0)

	# core query
	scene                  = pn.widgets.Select             (name="Scene", options=[], width=120)
	timestep               = pn.widgets.IntSlider          (name="Time", value=0, start=0, end=1, step=1, sizing_mode="stretch_width")
	timestep_delta         = pn.widgets.Select             (name="Speed", options=[1, 2, 4, 8, 1, 32, 64, 128], value=1, width=50)
	field                  = pn.widgets.Select             (name='Field', options=[], value='data', width=80)
	resolution             = pn.widgets.IntSlider          (name='Res', value=21, start=20, end=99,  sizing_mode="stretch_width")
	view_dependent         = pn.widgets.Select             (name="ViewDep",options={"Yes":True,"No":False}, value=True,width=80)
	num_refinements        = pn.widgets.IntSlider          (name='#Ref', value=0, start=0, end=4, width=80)
	direction              = pn.widgets.Select             (name='Direction', options={'X':0, 'Y':1, 'Z':2}, value=2, width=80)
	offset                 = pn.widgets.EditableFloatSlider(name="Offset", start=0.0, end=1024.0, step=1.0, value=0.0,  sizing_mode="stretch_width", format=NumeralTickFormatter(format="0.01"))
	
	# palette thingy
	range_mode             = pn.widgets.Select             (name="Range", options=["metadata", "user", "dynamic", "dynamic-acc"], value="dynamic-acc", width=120)
	range_min              = pn.widgets.FloatInput         (name="Min", width=80)
	range_max              = pn.widgets.FloatInput         (name="Max", width=80)

	palette                = pn.widgets.ColorMap           (name="Palette", options=GetPalettes(), value_name=DEFAULT_PALETTE, ncols=5,  width=180)
	color_mapper_type      = pn.widgets.Select             (name="Mapper", options=["linear", "log", ],width=60)
	
	# play thingy
	play_button            = pn.widgets.Button             (name="Play", width=8)
	play_sec               = pn.widgets.Select             (name="Frame delay", options=["0.00", "0.01", "0.1", "0.2", "0.1", "1", "2"], value="0.01")

	# bottom status bar
	request                = pn.widgets.TextInput          (name="", sizing_mode='stretch_width', disabled=False)
	response               = pn.widgets.TextInput          (name="", sizing_mode='stretch_width', disabled=False)

	# toolbar thingy
	info_button            = pn.widgets.Button   (icon="info-circle",width=20)
	open_button            = pn.widgets.Button   (icon="file-upload",width=20)
	save_button            = pn.widgets.Button   (icon="file-download",width=20)
	save_button_helper     = pn.widgets.IntInput (visible=False)
	copy_url_button        = pn.widgets.Button   (icon="copy",width=20)
	copy_url_button_helper = pn.widgets.IntInput (visible=False)
	logout_button          = pn.widgets.Button   (icon="logout",width=20)

	# current scene as JSON
	scene_body=pn.widgets.TextAreaInput(name='Current',sizing_mode="stretch_width",height=520,
		stylesheets=[""".bk-input {background-color: rgb(48, 48, 64);color: white;font-size: small;}"""])

	# constructor
	def __init__(self):

		self.on_change_callbacks={}

		self.num_hold=0
		global SLICE_ID
		self.id=SLICE_ID
		SLICE_ID += 1
		
		self.db = None
		self.access = None

		# translate and scale for each dimension
		self.logic_to_physic        = [(0.0, 1.0)] * 3
		self.metadata_range         = [0.0, 255.0]
		self.scenes                 = {}

		self.createGui()

		def onSceneChange(evt): 
			logger.info(f"onSceneChange {evt}")
			body=self.scenes[evt.new]
			self.setSceneBody(body)
		self.scene.param.watch(onSceneChange,"value")

		def onTimestepChange(evt):
			self.refresh()
		self.timestep.param.watch(onTimestepChange, "value")

		def onTimestepDeltaChange(evt):
			if bool(getattr(self,"setting_timestep_delta",False)): return
			setattr("setting_timestep_delta",True)
			value=int(evt.new)
			A = self.timestep.start
			B = self.timestep.end
			T = self.getTimestep()
			T = A + value * int((T - A) / value)
			T = min(B, max(A, T))
			self.timestep_delta.value = value
			self.timestep.step = value
			self.setTimestep(T)
			setattr("setting_timestep_delta",False)

		self.timestep_delta.param.watch(onTimestepDeltaChange,"value")

		def onFieldChange(evt):
			self.field.value = evt.new
			self.refresh()
		self.field.param.watch(onFieldChange,"value")

		def onPaletteChange(evt):
			self.color_bar=None
			self.refresh()
		self.palette.param.watch(onPaletteChange,"value_name")

		def onRangeModeChange(evt):
			mode=evt.new
			self.range_mode.value = mode
			self.color_map=None
			if mode == "metadata":   self.range_min.value = it.metadata_range[0]
			if mode == "dynamic-acc":self.range_min.value = 0.0
			self.range_min.disabled = False if mode == "user" else True
			if mode == "metadata":   self.range_max.value = it.metadata_range[1]
			if mode == "dynamic-acc":self.range_max.value = 0.0
			self.range_max.disabled = False if mode == "user" else True
			self.refresh()
		self.range_mode.param.watch(onRangeModeChange,"value")

		def onRangeChange(evt):
			self.color_map=None
			self.refresh()

		self.range_min.param.watch(onRangeChange,"value")
		self.range_max.param.watch(onRangeChange,"value")

		def onColorMapperTypeChange(evt):
			self.color_bar=None 
			self.refresh()
		self.color_mapper_type.param.watch(onColorMapperTypeChange,"value")
		
		def onResolutionChange(evt):
			self.refresh()

		self.resolution.param.watch(onResolutionChange,"value")
		self.view_dependent.param.watch(lambda evt: self.refresh(),"value")

		self.num_refinements.param.watch(lambda evt: self.refresh(),"value")
		self.direction.param.watch(lambda evt: self.setDirection(evt.new),"value")

		def onOffsetChange(evt): 
			self.offset.value = evt.new
			self.refresh()
		self.offset.param.watch(onOffsetChange,"value")

		self.info_button.on_click(lambda evt: self.showInfo())
		self.open_button.on_click(lambda evt: self.showOpen())
		self.save_button.on_click(lambda evt: self.save())
		self.copy_url_button.on_click(lambda evt: self.copyUrl())
		self.play_button.on_click(lambda evt: self.togglePlay())

		self.setShowOptions(DEFAULT_SHOW_OPTIONS)

		self.start()


	# open
	def showOpen(self):

		def onLoadClick(evt=None):
			body=value.decode('ascii')
			self.scene_body.value=body
			# self.setSceneBody(json.loads(body)) NOT SURE I WANT THIS
			ShowInfoNotification('Load done')

		file_input = pn.widgets.FileInput(description="Load", accept=".json", callback=onLoadClick)

		# onEvalClick
		def onEvalClick(evt=None):
			body=json.loads(self.scene_body.value)
			self.setSceneBody(body)
			ShowInfoNotification('Eval done')

		eval_button = pn.widgets.Button(name="Eval", callback=onEvalClick, align='end')
		self.showDialog(
			Column(
				self.scene_body,
				Row(file_input, eval_button, align='end'),
				sizing_mode="stretch_both",align="end"
			), 
			width=600, height=700, name="Open")
	

	# save
	def save(self):
		body=json.dumps(self.getSceneBody(),indent=2)
		self.save_button_helper.value=body
		ShowInfoNotification('Save done')
		print(body)

	# copy url
	def copyUrl(self):
		self.copy_url_button_helper.value=self.getShareableUrl()
		ShowInfoNotification('Copy url done')


	# createGui
	def createGui(self):

		self.save_button.js_on_click(args={"source": self.save_button_helper}, code="""
			function jsSave() {
				console.log(source.value);
				const link = document.createElement("a");
				const file = new Blob([source.value], { type: 'text/plain' });
				link.href = URL.createObjectURL(file);
				link.download = "sample.txt";
				link.click();
				URL.revokeObjectURL(link.href);
			}
			setTimeout(jsSave,300);
		""")


		self.copy_url_button.js_on_click(args={"source": self.copy_url_button_helper}, code="""
			function jsCopyUrl() {
				console.log(source.value);
				navigator.clipboard.writeText(source.value);
			} 
			setTimeout(jsCopyUrl,300);
		""")

		self.logout_button = pn.widgets.Button(icon="logout",width=20)
		self.logout_button.js_on_click(args={"source": self.logout_button}, code="""
			console.log("logging out...")
			window.location=window.location.href + "/logout";
		""")

		# for icons see https://tabler.io/icons

		# play time
		self.play = types.SimpleNamespace()
		self.play.is_playing = False

		self.idle_callback = None
		self.color_bar     = None
		self.query_node    = None
		self.canvas        = None

		self.t1=time.time()
		self.aborted       = Aborted()
		self.new_job       = False
		self.current_img   = None
		self.last_job_pushed =time.time()
		self.query_node=QueryNode()
		self.canvas = Canvas(self.id)
		self.canvas.on_viewport_change=lambda: self.refresh()

		self.top_layout=Column(sizing_mode="stretch_width")

		self.middle_layout=Column(
			Row(self.canvas.main_layout, sizing_mode='stretch_both'),
			sizing_mode='stretch_both'
		)

		self.bottom_layout=Column(sizing_mode="stretch_width")

		self.dialogs=Column()
		self.dialogs.visible=False

		self.main_layout=Column(
			self.top_layout,
			self.middle_layout,
			self.bottom_layout, 

			self.dialogs,
			self.copy_url_button_helper,
			self.save_button_helper,

			sizing_mode="stretch_both"
		)

	# getShowOptions
	def getShowOptions(self):
		return self.show_options

	# setShowOptions
	def setShowOptions(self, value):
		self.show_options=value
		for layout, position in ((self.top_layout,"top"),(self.bottom_layout,"bottom")):
			layout.clear()
			for row in value.get(position,[[]]):
				v=[]
				for widget in row:
					if isinstance(widget,str):
						widget=getattr(self, widget.replace("-","_"),None)
					if widget:
						v.append(widget)
				if v: layout.append(Row(*v,sizing_mode="stretch_width"))

		# bottom

	# getShareableUrl
	def getShareableUrl(self):
		body=self.getSceneBody()
		load_s=base64.b64encode(json.dumps(body).encode('utf-8')).decode('ascii')
		current_url=GetCurrentUrl()
		o=urlparse(current_url)
		return o.scheme + "://" + o.netloc + o.path + '?' + urlencode({'load': load_s})		

	# stop
	def stop(self):
		self.aborted.setTrue()
		self.query_node.stop()

	# start
	def start(self):
		self.query_node.start()
		if not self.idle_callback:
			self.idle_callback = AddPeriodicCallback(self.onIdle, 1000 // 30)
		self.refresh()

	# getMainLayout
	def getMainLayout(self):
		return self.main_layout

	# getLogicToPhysic
	def getLogicToPhysic(self):
		return self.logic_to_physic

	# setLogicToPhysic
	def setLogicToPhysic(self, value):
		logger.debug(f"id={self.id} value={value}")
		self.logic_to_physic = value
		self.refresh()

	# getPhysicBox
	def getPhysicBox(self):
		dims = self.db.getLogicSize()
		vt = [it[0] for it in self.logic_to_physic]
		vs = [it[1] for it in self.logic_to_physic]
		return [[
			0 * vs[I] + vt[I],
			dims[I] * vs[I] + vt[I]
		] for I in range(len(dims))]

	# setPhysicBox
	def setPhysicBox(self, value):
		dims = self.db.getLogicSize()
		def LinearMapping(a, b, A, B):
			vs = (B - A) / (b - a)
			vt = A - a * vs
			return vt, vs
		T = [LinearMapping(0, dims[I], *value[I]) for I in range(len(dims))]
		self.setLogicToPhysic(T)
		
	# getSceneBody
	def getSceneBody(self):
		(x1,x2),(y1,y2)=self.canvas.getViewport()
		return {
			"scene" : {
				"name": self.scene.value, 
				
				# NOT needed.. they should come automatically from the dataset?
				#   "timesteps": self.db.getTimesteps(),
				#   "physic_box": self.getPhysicBox(),
				#   "fields": self.field.options,
				#   "directions" : self.direction.options,
				# "metadata-range": self.metadata_range,

				"timestep-delta": self.timestep_delta.value,
				"timestep": self.timestep.value,
				"direction": self.direction.value,
				"offset": self.offset.value, 
				"field": self.field.value,
				"view-dependent": self.view_dependent.value,
				"resolution": self.resolution.value,
				"num-refinements": self.num_refinements.value,
				"play-sec":self.play_sec.value,
				"palette": self.palette.value_name,
				"color-mapper-type": self.color_mapper_type.value,
				"range-mode": self.range_mode.value,
				"range-min": cdouble(self.range_min.value), # Object of type float32 is not JSON serializable
				"range-max": cdouble(self.range_max.value),
				"x":(x1+x2)/2.0,
				"y":(y1+y2)/2.0,
				"w":x2-x1,
				"h":y2-y1	
			}
		}

	# hold
	def hold(self):
		self.num_hold=getattr(self,"num_hold",0) + 1
		# if self.num_hold==1: self.doc.hold()

	# unhold
	def unhold(self):
		self.num_hold-=1
		# if self.num_hold==0: self.doc.unhold()

	# load
	def load(self, value):

		if isinstance(value,str):
			ext=os.path.splitext(value)[1].split("?")[0]
			if ext==".json":
				value=LoadJSON(value)
			else:
				value={"scenes": [{"name": os.path.basename(value), "url":value}]}

		# from dictionary
		elif isinstance(value,dict):
			pass
		else:
			raise Exception(f"{value} not supported")

		assert(isinstance(value,dict))
		assert(len(value)==1)
		root=list(value.keys())[0]

		self.scenes={}
		for it in value[root]:
			if "name" in it:
				self.scenes[it["name"]]={"scene": it}

		self.scene.options = list(self.scenes)

		if self.scenes:
			first_scene_name=list(self.scenes)[0]
			self.scene.value=first_scene_name

	# setSceneBody
	def setSceneBody(self, scene):

		logger.info(f"# //////////////////////////////////////////#")
		logger.info(f"id={self.id} {scene} START")

		# TODO!
		# self.stop()

		assert(isinstance(scene,dict))
		assert(len(scene)==1 and list(scene.keys())==["scene"])

		# go one level inside
		scene=scene["scene"]

		# the url should come from first load (for security reasons)
		name=scene["name"]

		assert(name in self.scenes)
		default_scene=self.scenes[name]["scene"]
		url =default_scene["url"]
		urls=default_scene.get("urls",{})

		# special case, I want to force the dataset to be local (case when I have a local dashboards and remove dashboards)
		if "urls" in scene:

			if "--prefer" in sys.argv:
				prefer = sys.argv[sys.argv.index("--prefer") + 1]
				prefers = [it for it in urls if it['id']==prefer]
				if prefers:
					logger.info(f"id={self.id} Overriding url from {prefers[0]['url']} since selected from --select command line")
					url = prefers[0]['url']
					
			else:
				locals=[it for it in urls if it['id']=="local"]
				if locals and os.path.isfile(locals[0]["url"]):
					logger.info(f"id={self.id} Overriding url from {locals[0]['url']} since it exists and is a local path")
					url = locals[0]["url"]

		logger.info(f"id={self.id} LoadDataset url={url}...")
		db=LoadDataset(url=url) 

		# update the GUI too
		self.db    =db
		self.access=db.createAccess()
		self.scene.value=name

		timesteps=self.db.getTimesteps()
		self.timestep.start = timesteps[ 0]
		self.timestep.end   = timesteps[-1]
		self.timestep.step  = 1

		self.field.options=list(self.db.getFields())

		pdim = self.getPointDim()

		if "logic-to-physic" in scene:
			logic_to_physic=scene["logic-to-physic"]
			self.setLogicToPhysic(logic_to_physic)
		else:
			physic_box = self.db.inner.idxfile.bounds.toAxisAlignedBox().toString().strip().split()
			physic_box = [(float(physic_box[I]), float(physic_box[I + 1])) for I in range(0, pdim * 2, 2)]
			self.setPhysicBox(physic_box)

		if "directions" in scene:
			directions=scene["directions"]
		else:
			directions = self.db.inner.idxfile.axis.strip().split()
			directions = {it: I for I, it in enumerate(directions)} if directions else  {'X':0,'Y':1,'Z':2}
		self.direction.options=directions

		self.timestep_delta.value=int(scene.get("timestep-delta", 1))
		self.timestep.value=int(scene.get("timestep", self.db.getTimesteps()[0]))
		self.view_dependent.value = bool(scene.get('view-dependent', True))

		resolution=int(scene.get("resolution", -6))
		if resolution<0: resolution=self.db.getMaxResolution()+resolution
		self.resolution.end = self.db.getMaxResolution()
		self.resolution.value = resolution

		self.field.value=scene.get("field", self.db.getField().name)
		self.num_refinements.value=int(scene.get("num-refinements", 2))

		direction=int(scene.get("direction", 2))
		self.setDirection(direction)

		self.offset.value=float(scene.get("offset",self.guessOffset(direction)[0]))
		self.play_sec.value=float(scene.get("play-sec",0.01))
		self.palette.value_name=scene.get("palette",DEFAULT_PALETTE)

		db_field = self.db.getField(self.field.value)
		self.metadata_range = list(scene.get("metadata-range",[db_field.getDTypeRange().From, db_field.getDTypeRange().To]))
		assert(len(self.metadata_range))==2
		self.color_map=None

		self.range_mode.value=scene.get("range-mode","dynamic-acc")

		if self.range_mode.value=="user":
			self.range_min.value=scene.get("range-min",low)
			self.range_max.value=scene.get("range-max",high)

		self.color_mapper_type.value = scene.get("color-mapper-type","linear")	

		x=scene.get("x",None)
		y=scene.get("y",None)
		w=scene.get("w",None)
		h=scene.get("h",None)

		if x is not None:
			x1,x2=x-w/2.0, x+w/2.0
			y1,y2=y-h/2.0, y+h/2.0
			self.canvas.setViewport([(x1,x2),(y1,y2)])

		show_options=scene.get("show-options",DEFAULT_SHOW_OPTIONS)
		self.setShowOptions(show_options)

		self.start()

		logger.info(f"id={self.id} END\n")


	# showInfo
	def showInfo(self):

		logger.debug(f"Show info")
		body=self.scenes[self.scene.value]
		metadata=body["scene"].get("metadata", [])

		cards=[]
		for I, item in enumerate(metadata):

			type = item["type"]
			filename = item.get("filename",f"metadata_{I:02d}.bin")

			if type == "b64encode":
				# binary encoded in string
				body = base64.b64decode(item["encoded"]).decode("utf-8")
				body = io.StringIO(body)
				body.seek(0)
				internal_panel=HTML(f"<div><pre><code>{body}</code></pre></div>",sizing_mode="stretch_width",height=400)
			elif type=="json-object":
				obj=item["object"]
				file = io.StringIO(json.dumps(obj))
				file.seek(0)
				internal_panel=JSON(obj,name="Object",depth=3, sizing_mode="stretch_width",height=400) 
			else:
				continue

			cards.append(Card(
					internal_panel,
					pn.widgets.FileDownload(file, embed=True, filename=filename,align="end"),
					title=filename,
					collapsed=(I>0),
					sizing_mode="stretch_width"
				)
			)

		self.showDialog(*cards)

	# showDialog
	def showDialog(self, *args,**kwargs):
		d={"position":"center", "width":1024, "height":600, "contained":False}
		d.update(**kwargs)
		float_panel=FloatPanel(*args, **d)
		self.dialogs.append(float_panel)

	# getMaxResolution
	def getMaxResolution(self):
		return self.db.getMaxResolution()

	# setViewDependent
	def setViewDependent(self, value):
		logger.debug(f"id={self.id} value={value}")
		self.view_dependent.value = value
		self.refresh()


	# setDirection
	def setDirection(self, value):
		logger.debug(f"id={self.id} value={value}")
		pdim = self.getPointDim()
		if pdim == 2: value = 2
		dims = [int(it) for it in self.db.getLogicSize()]
		self.direction.value = value

		# default behaviour is to guess the offset
		offset_value,offset_range=self.guessOffset(value)
		self.offset.start=offset_range[0]
		self.offset.end  =offset_range[1]
		self.offset.step=1e-16 if self.offset.editable and offset_range[2]==0.0 else offset_range[2] #  problem with editable slider and step==0

		self.offset.value=offset_value
		self.setQueryLogicBox(([0]*pdim,dims))
		self.refresh()

	# getLogicAxis (depending on the projection XY is the slice plane Z is the orthogoal direction)
	def getLogicAxis(self):
		dir  = self.direction.value
		directions = self.direction.options
		# this is the projected slice
		XY = list(directions.values())
		if len(XY) == 3:
			del XY[dir]
		else:
			assert (len(XY) == 2)
		X, Y = XY
		# this is the cross dimension
		Z = dir if len(directions) == 3 else 2
		titles = list(directions.keys())
		return (X, Y, Z), (titles[X], titles[Y], titles[Z] if len(titles) == 3 else 'Z')

	# guessOffset
	def guessOffset(self, dir):

		pdim = self.getPointDim()

		# 2d there is no direction
		if pdim == 2:
			assert dir == 2
			value = 0
			return value,[0, 0, 1]
		else:
			vt = [self.logic_to_physic[I][0] for I in range(pdim)]
			vs = [self.logic_to_physic[I][1] for I in range(pdim)]

			if all([it == 0 for it in vt]) and all([it == 1.0 for it in vs]):
				dims = [int(it) for it in self.db.getLogicSize()]
				value = dims[dir] // 2
				return value,[0, int(dims[dir]) - 1, 1]
			else:
				A, B = self.getPhysicBox()[dir]
				value = (A + B) / 2.0
				return value,[A, B, 0]

	# toPhysic
	def toPhysic(self, value):

		# is a box
		if hasattr(value[0], "__iter__"):
			p1, p2 = [self.toPhysic(p) for p in value]
			return [p1, p2]

		pdim = self.getPointDim()
		dir = self.direction.value
		assert (pdim == len(value))

		vt = [self.logic_to_physic[I][0] for I in range(pdim)]
		vs = [self.logic_to_physic[I][1] for I in range(pdim)]

		# apply scaling and translating
		ret = [vs[I] * value[I] + vt[I] for I in range(pdim)]

		if pdim == 3:
			del ret[dir]  # project

		assert (len(ret) == 2)
		return ret

	# toLogic
	def toLogic(self, value):
		assert (len(value) == 2)
		pdim = self.getPointDim()
		dir = self.direction.value

		# is a box?
		if hasattr(value[0], "__iter__"):
			p1, p2 = [self.toLogic(p) for p in value]
			if pdim == 3:
				p2[dir] += 1  # make full dimensional
			return [p1, p2]

		ret = list(value)

		# unproject
		if pdim == 3:
			ret.insert(dir, 0)

		assert (len(ret) == pdim)

		vt = [self.logic_to_physic[I][0] for I in range(pdim)]
		vs = [self.logic_to_physic[I][1] for I in range(pdim)]

		# scaling/translatation
		try:
			ret = [(ret[I] - vt[I]) / vs[I] for I in range(pdim)]
		except Exception as ex:
			logger.info(f"Exception {ex} with logic_to_physic={self.logic_to_physic}", self.logic_to_physic)
			raise

		# unproject
		if pdim == 3:
			offset = self.offset.value  # this is in physic coordinates
			ret[dir] = int((offset - vt[dir]) / vs[dir])

		assert (len(ret) == pdim)
		return ret

	# togglePlay
	def togglePlay(self):
		if self.play.is_playing:
			self.stopPlay()
		else:
			self.startPlay()

	# startPlay
	def startPlay(self):
		logger.info(f"id={self.id}::startPlay")
		self.play.is_playing = True
		self.play.t1 = time.time()
		self.play.wait_render_id = None
		self.play.num_refinements = self.num_refinements.value
		self.num_refinements.value = 1
		self.setWidgetsDisabled(True)
		self.play_button.disabled = False
		self.play_button.label = "Stop"

	# stopPlay
	def stopPlay(self):
		logger.info(f"id={self.id}::stopPlay")
		self.play.is_playing = False
		self.play.wait_render_id = None
		self.num_refinements.value = self.play.num_refinements
		self.setWidgetsDisabled(False)
		self.play_button.disabled = False
		self.play_button.label = "Play"

	# playNextIfNeeded
	def playNextIfNeeded(self):

		if not self.play.is_playing:
			return

		# avoid playing too fast by waiting a minimum amount of time
		t2 = time.time()
		if (t2 - self.play.t1) < float(self.play_sec.value):
			return

		# wait
		if self.play.wait_render_id is not None and self.render_id.value<self.play.wait_render_id:
			return

		# advance
		T = int(self.timestep.value) + self.timestep_delta.value

		# reached the end -> go to the beginning?
		if T >= self.timestep.end:
			T = self.timesteps.timestep.start

		logger.info(f"id={self.id}::playing timestep={T}")

		# I will wait for the resolution to be displayed
		self.play.wait_render_id = self.render_id.value+1
		self.play.t1 = time.time()
		self.timestep.value= T

	# onShowMetadataClick
	def onShowMetadataClick(self):
		self.metadata.visible = not self.metadata.visible

	# setWidgetsDisabled
	def setWidgetsDisabled(self, value):
		self.scene.disabled = value
		self.palette.disabled = value
		self.timestep.disabled = value
		self.timestep_delta.disabled = value
		self.field.disabled = value
		self.direction.disabled = value
		self.offset.disabled = value
		self.num_refinements.disabled = value
		self.resolution.disabled = value
		self.view_dependent.disabled = value
		self.request.disabled = value
		self.response.disabled = value
		self.play_button.disabled = value
		self.play_sec.disabled = value

	# getPointDim
	def getPointDim(self):
		return self.db.getPointDim() if self.db else 2

	# updateSceneBodyText
	def updateSceneBodyText(self):
		body=json.dumps(self.getSceneBody(),indent=2)
		self.scene_body.value=body

	# refresh
	def refresh(self):
		self.aborted.setTrue()
		self.new_job=True
		self.updateSceneBodyText()

	# getQueryLogicBox
	def getQueryLogicBox(self):
		assert(self.canvas)
		(x1,x2),(y1,y2)=self.canvas.getViewport()
		return self.toLogic([(x1,y1),(x2,y2)])

	# setQueryLogicBox
	def setQueryLogicBox(self,value):
		assert(self.canvas)
		logger.debug(f"id={self.id} value={value}")
		proj=self.toPhysic(value) 
		(x1,y1),(x2,y2)=proj[0],proj[1]
		self.canvas.setViewport([(x1,x2),(y1,y2)])
		self.refresh()
  
	# getLogicCenter
	def getLogicCenter(self):
		pdim=self.getPointDim()  
		p1,p2=self.getQueryLogicBox()
		assert(len(p1)==pdim and len(p2)==pdim)
		return [(p1[I]+p2[I])*0.5 for I in range(pdim)]

	# getLogicSize
	def getLogicSize(self):
		pdim=self.getPointDim()
		p1,p2=self.getQueryLogicBox()
		assert(len(p1)==pdim and len(p2)==pdim)
		return [(p2[I]-p1[I]) for I in range(pdim)]

  # gotoPoint
	def gotoPoint(self,point):
		return 
		logger.debug(f"id={self.id} point={point}")
		pdim=self.getPointDim()

		if pdim==3:
			dir=self.direction.value
			self.offset.value=point[dir]
		
		# the point should be centered in p3d
		(p1,p2),dims=self.getQueryLogicBox(),self.getLogicSize()
		p1,p2=list(p1),list(p2)
		for I in range(pdim):
			p1[I],p2[I]=point[I]-dims[I]/2,point[I]+dims[I]/2
		self.setQueryLogicBox([p1,p2])
		self.canvas.renderPoints([self.toPhysic(point)]) # COMMENTED OUT
  
	# gotNewData
	def gotNewData(self, result):

		data=result['data']
		try:
			data_range=np.min(data),np.max(data)
		except:
			data_range=0.0,0.0

		logic_box=result['logic_box'] 

		# depending on the palette range mode, I need to use different color mapper low/high
		mode=self.range_mode.value

		# show the user what is the current offset
		maxh=self.db.getMaxResolution()
		dir=self.direction.value

		pdim=self.getPointDim()
		vt,vs=self.logic_to_physic[dir] if pdim==3 else (0.0,1.0)
		endh=result['H']

		user_physic_offset=self.offset.value

		real_logic_offset=logic_box[0][dir] if pdim==3 else 0.0
		real_physic_offset=vs*real_logic_offset + vt 
		user_logic_offset=int((user_physic_offset-vt)/vs)

		self.offset.name=" ".join([
			f"Offset: {user_physic_offset:.3f}±{abs(user_physic_offset-real_physic_offset):.3f}",
			f"Pixel: {user_logic_offset}±{abs(user_logic_offset-real_logic_offset)}",
			f"Max Res: {endh}/{maxh}"
		])

		# refresh the range
		if True:

			# in dynamic mode, I need to use the data range
			if mode=="dynamic":
				self.range_min.value = data_range[0]
				self.range_max.value = data_range[1]
				
			# in data accumulation mode I am accumulating the range
			if mode=="dynamic-acc":
				if self.range_min.value==self.range_max.value:
					self.range_min.value=data_range[0]
					self.range_max.value=data_range[1]
				else:
					self.range_min.value = min(self.range_min.value, data_range[0])
					self.range_max.value = max(self.range_max.value, data_range[1])

			# update the color bar
			low =cdouble(self.range_min.value)
			high=cdouble(self.range_max.value)

		# regenerate colormap
		if self.color_bar is None:
			color_mapper_type=self.color_mapper_type.value
			assert(color_mapper_type in ["linear","log"])
			is_log=color_mapper_type=="log"
			palette=self.palette.value
			mapper_low =max(EPSILON, low ) if is_log else low
			mapper_high=max(EPSILON, high) if is_log else high
			
			self.color_bar = ColorBar(color_mapper = 
				LogColorMapper   (palette=palette, low=mapper_low, high=mapper_high) if is_log else 
				LinearColorMapper(palette=palette, low=mapper_low, high=mapper_high)
			)

		logger.debug(f"id={self.id}::rendering result data.shape={data.shape} data.dtype={data.dtype} logic_box={logic_box} data-range={data_range} range={[low,high]}")

		# update the image
		(x1,y1),(x2,y2)=self.toPhysic(logic_box)
		self.canvas.setImage(data,x1,y1,x2,y2, self.color_bar)

		(X,Y,Z),(tX,tY,tZ)=self.getLogicAxis()
		self.canvas.setAxisLabels(tX,tY)

		# update the status bar
		tot_pixels=data.shape[0]*data.shape[1]
		canvas_pixels=self.canvas.getWidth()*self.canvas.getHeight()
		self.H=result['H']
		query_status="running" if result['running'] else "FINISHED"
		self.response.value=" ".join([
			f"#{result['I']+1}",
			f"{str(logic_box).replace(' ','')}",
			f"{data.shape[0]}x{data.shape[1]}",
			f"Res={result['H']}/{maxh}",
			f"{result['msec']}msec",
			str(query_status)
		])

		self.render_id.value=self.render_id.value+1 
  

	# pushJobIfNeeded
	def pushJobIfNeeded(self):
		assert(self.query_node and self.canvas)
		canvas_w,canvas_h=(self.canvas.getWidth(),self.canvas.getHeight())
		query_logic_box=self.getQueryLogicBox()
		offset=self.offset.value
		pdim=self.getPointDim()

		if not self.new_job:
			return

		# abort the last one
		self.aborted.setTrue()
		self.query_node.waitIdle()
		num_refinements = self.num_refinements.value
		if num_refinements==0:
			num_refinements=3 if pdim==2 else 4
		self.aborted=Aborted()

		# do not push too many jobs
		if (time.time()-self.last_job_pushed)<0.2:
			return
		
		# I will use max_pixels to decide what resolution, I am using resolution just to add/remove a little the 'quality'
		if self.view_dependent.value:
			endh=None 
			canvas_w,canvas_h=(self.canvas.getWidth(),self.canvas.getHeight())

			# probably the UI is not ready yet
			if not canvas_w or not canvas_h:
				return
			
			max_pixels=canvas_w*canvas_h
			resolution=self.resolution.value
			delta=resolution-self.getMaxResolution()
			if resolution<self.getMaxResolution():
				max_pixels=int(max_pixels/pow(1.3,abs(delta))) # decrease 
			elif resolution>self.getMaxResolution():
				max_pixels=int(max_pixels*pow(1.3,abs(delta))) # increase 
		else:
			# I am not using the information about the pixel on screen
			max_pixels=None
			resolution=self.resolution.value
			endh=resolution
		
		self.updateSceneBodyText()
		
		logger.debug(f"id={self.id} pushing new job query_logic_box={query_logic_box} max_pixels={max_pixels} endh={endh}..")

		timestep=int(self.timestep.value)
		field=self.field.value
		box_i=[[int(it) for it in jt] for jt in query_logic_box]
		self.request.value=f"t={timestep} b={str(box_i).replace(' ','')} {canvas_w}x{canvas_h}"
		self.response.value="Running..."

		self.query_node.pushJob(
			self.db, 
			access=self.access,
			timestep=timestep, 
			field=field, 
			logic_box=query_logic_box, 
			max_pixels=max_pixels, 
			num_refinements=num_refinements, 
			endh=endh, 
			aborted=self.aborted
		)
		
		self.last_job_pushed=time.time()
		self.new_job=False
		logger.debug(f"id={self.id} pushed new job query_logic_box={query_logic_box}")

	# onIdle
	def onIdle(self):

		if not self.db:
			return

		if self.canvas and  self.canvas.getWidth()>0 and self.canvas.getHeight()>0:
			self.playNextIfNeeded()

		if self.query_node:
			result=self.query_node.popResult(last_only=True) 
			if result is not None: 
				self.gotNewData(result)
			self.pushJobIfNeeded()






