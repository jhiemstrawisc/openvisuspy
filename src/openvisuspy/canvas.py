import os,sys,logging,copy,traceback,colorcet

import numpy as np

logger = logging.getLogger(__name__)

from .utils import *

import bokeh
import bokeh.models

from bokeh.models import ColumnDataSource,Range1d
from bokeh.events import DoubleTap
from bokeh.plotting import figure as Figure

from bokeh.models import BoxSelectTool
from bokeh.events import SelectionGeometry
from bokeh.models.callbacks import CustomJS

import panel as pn
from panel import Column,Row
from panel.pane import Bokeh

# ////////////////////////////////////////////////////////////////////////////////////
class Canvas:
  
	# constructor
	def __init__(self, id):
		self.id=id
		self.fig=None
		self.on_double_tab=[]
		self.on_selection_geometry=[]
		self.main_layout=Row(sizing_mode="stretch_both")	
		self.createFigure() 
		self.source_image = ColumnDataSource(data={"image": [np.random.random((300,300))*255], "x":[0], "y":[0], "dw":[256], "dh":[256]})  
		self.last_renderer=self.fig.image("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh")

		# since I cannot track consistently inner_width,inner_height (particularly on Jupyter) I am using a timer
		self.on_viewport_change=None
		self.setViewport([(0,256),(0,256)])
		AddPeriodicCallback(self.onIdle,1000//30)


	# onIdle
	def onIdle(self):
		W,H=self.getWidth(),self.getHeight()

		# I need to wait until I get a decent size
		if W==0 or H==0:  
			return

		# some zoom in/out or panning happened (handled by bokeh) 
		# note: no need to fix the aspect ratio in this case
		fig_viewport=self.__getFigureViewport()
		if fig_viewport!=self.user_viewport:
			(x1,x2),(y1,y2)=fig_viewport 
			self.user_viewport=[(x1,x2),(y1,y2)]
			if self.on_viewport_change:
				self.on_viewport_change()
			return

		# I need to fix the aspect ratio , since only now I may have got the real canvas dimension
		if True:
			(x1,x2),(y1,y2)=self.user_viewport # using the last value set by the user
			w,cx =(x2-x1),(x1+x2)/2.0
			h,cy =(y2-y1),(y1+y2)/2.0
			if (w/W) > (h/H): 
				h=(w/W)*H 
			else: 
				w=(h/H)*W
			x1,x2=cx-w/2,cx+w/2
			y1,y2=cy-h/2,cy+h/2
			value=[(x1,x2),(y1,y2)]

		# nothing changed
		if value==self.user_viewport: 
			return

		# viewport changed, notify to the external too
		self.user_viewport=value
		self.__setFigureViewport(value)
		if self.on_viewport_change:
			self.on_viewport_change()

	# on_event
	def on_event(self, evt, callback):
		if evt==DoubleTap:
			self.on_double_tab.append(callback)
		elif evt==SelectionGeometry:
			self.on_selection_geometry.append(callback)
		else:
			raise Exception("error")

	# createFigure
	def createFigure(self):
		old=self.fig
		self.fig=Figure(active_scroll = "wheel_zoom") 
		self.fig.x_range = Range1d(0,512) if old is None else old.x_range
		self.fig.y_range = Range1d(0,512) if old is None else old.y_range
		self.fig.toolbar_location="right" # None                 if old is None else old.toolbar_location
		self.fig.sizing_mode = 'stretch_both'          if old is None else old.sizing_mode
		self.fig.xaxis.axis_label  = "X"               if old is None else old.xaxis.axis_label
		self.fig.yaxis.axis_label  = "Y"               if old is None else old.yaxis.axis_label

		# if old: old_remove_on_event(DoubleTap, self.onDoubleTap) cannot find old_remove_on_event
		def onDoubleTap(evt):
			for callback in self.on_double_tab: callback(evt)
		self.fig.on_event(DoubleTap, onDoubleTap)

		# TODO: keep the renderers but not the
		if old is not None:
			v=old.renderers
			old.renderers=[]
			for it in v:
				if it!=self.last_renderer:
					self.fig.renderers.append(it)

		self.main_layout[:]=[]
		self.main_layout.append(Bokeh(self.fig))
		
		self.last_dtype   = None
		self.last_cb      = None
		self.last_renderer= None

		tool=BoxSelectTool()
		self.fig.add_tools(tool)

		# does not working
		if False:
			self.fig.on_event(SelectionGeometry, lambda s: print("JHERE"))
		else:

			def emitSelectionGeometry(attr,old,new):
				evt=json.loads(new)
				logger.info(f"emitSelectionGeometry {evt}")
				for fn in self.on_selection_geometry: fn(evt)

			tool_helper=bokeh.models.TextInput()
			tool_helper.on_change('value', emitSelectionGeometry)

			self.fig.js_on_event(SelectionGeometry, CustomJS(
				args=dict(tool_helper=tool_helper), 
				code="""tool_helper.value=JSON.stringify(cb_obj.geometry, undefined, 2);"""
			))


	# setAxisLabels
	def setAxisLabels(self,x,y):
		self.fig.xaxis.axis_label  = x
		self.fig.yaxis.axis_label  = y		

	# getWidth (this is number of pixels along X for the canvas)
	def getWidth(self):
		try:
			return self.fig.inner_width
		except:
			return 0

	# getHeight (this is number of pixels along Y  for the canvas)
	def getHeight(self):
		try:
			return self.fig.inner_height
		except:
			return 0

	# __getFigureViewport
	def __getFigureViewport(self):
		return [
			(self.fig.x_range.start, self.fig.x_range.end),
			(self.fig.y_range.start, self.fig.y_range.end)
		]

	# __setFigureViewport
	def __setFigureViewport(self,value):
		(x1,x2),(y1,y2)=value
		self.fig.x_range.start, self.fig.x_range.end = (x1,x2)
		self.fig.y_range.start, self.fig.y_range.end = (y1,y2)


	# getViewport [(x1,x2),(y1,y2)]
	def getViewport(self):
		return self.user_viewport

	  # setViewport
	def setViewport(self,value):
		(x1,x2),(y1,y2)=value
		self.user_viewport=[(x1,x2),(y1,y2)]
		self.__setFigureViewport(value)

	# setImage
	def setImage(self, data, x1, y1, x2, y2, color_bar):

		img=ConvertDataForRendering(data)
		dtype=img.dtype
		if self.last_dtype==dtype and self.last_cb==color_bar:
			# current dtype is 'compatible' with the new image dtype, just change the source _data
			self.source_image.data={"image":[img], "x":[x1], "y":[y1], "dw":[x2-x1], "dh":[y2-y1]}
		else:
			self.createFigure()
			self.source_image = ColumnDataSource(data={"image":[img], "x":[x1], "y":[y1], "dw":[x2-x1], "dh":[y2-y1]})
			if img.dtype==np.uint32:	
				self.last_renderer=self.fig.image_rgba("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh") 
			else:
				self.last_renderer=self.fig.image("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh", color_mapper=color_bar.color_mapper) 
			self.fig.add_layout(color_bar, 'right')
			self.last_dtype=img.dtype
			self.last_cb=color_bar

