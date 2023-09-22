

import os,sys,logging
import numpy as np

from . utils import *

import bokeh
import bokeh.plotting
import bokeh.models 
import bokeh.events 

logger = logging.getLogger(__name__)

# ////////////////////////////////////////////////////////////////////////////////////
class Canvas:
  
	# constructor
	def __init__(self, id, color_bar, sizing_mode='stretch_both', toolbar_location=None):
		self.id=id
		self.sizing_mode=sizing_mode
		self.color_bar=color_bar
		self.fig=bokeh.plotting.figure(active_scroll = "wheel_zoom") 
		self.fig.x_range = bokeh.models.Range1d(0,512)   
		self.fig.y_range = bokeh.models.Range1d(0,512) 
		self.fig.toolbar_location=toolbar_location
		self.fig.sizing_mode = self.sizing_mode
		# self.fig.add_tools(bokeh.models.HoverTool(tooltips=[ ("(x, y)", "($x, $y)"),("RGB", "(@R, @G, @B)")])) # is it working?
		self.on_resize=None
		self.last_width=0
		self.last_height=0

		self.source_image = bokeh.models.ColumnDataSource(data={"image": [np.random.random((300,300))*255], "x":[0], "y":[0], "dw":[256], "dh":[256]})  
		self.fig.image("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh", color_mapper=self.color_bar.color_mapper)  
		self.fig.add_layout(self.color_bar, 'right')
 
		self.points       = None
		self.dtype        = None
		self.color_mapper = self.color_bar.color_mapper

	# checkFigureResize
	def checkFigureResize(self):

		# huge problems with inner_ thingy ... HTML does not reflect real values
		# problems here, not getting real-time resizes
		# https://github.com/bokeh/bokeh/issues/9136
		# https://github.com/bokeh/bokeh/pull/9308
		# self.fig.on_change('inner_width' , self.onResize)
		# self.fig.on_change('inner_height', self.onResize)

		try:
			w=self.fig.inner_width
			h=self.fig.inner_height
		except Exception as ex:
			return
		if not w or not h: return
		if w==self.last_width and h==self.last_height: return

		# getting spurious events with marginal changes (in particular with jupyter notebook)
		# is change too marginal?
		if True:
			from .utils import IsJupyter
			max_diff_pixels=3
			if IsJupyter() and self.last_width>0 and self.last_height>0 and abs(w-self.last_width)<=max_diff_pixels or abs(h-self.last_height)<max_diff_pixels:
				return

		self.last_width =w
		self.last_height=h
		self.onResize()

	# onResize
	def onResize(self):
		if self.on_resize is not None:
			self.on_resize()

	# getWidth (this is number of pixels along X for the canvas)
	def getWidth(self):
		return self.last_width

	# getHeight (this is number of pixels along Y  for the canvas)
	def getHeight(self):
		return self.last_height

	# enableDoubleTap
	def enableDoubleTap(self,fn):
		self.fig.on_event(bokeh.events.DoubleTap, lambda evt: fn(evt.x,evt.y))

	  # getViewport (x1,y1,x2,y2)
	def getViewport(self):

		return [
			self.fig.x_range.start, 
			self.fig.y_range.start,
			self.fig.x_range.end,
			self.fig.y_range.end
		]

	  # setViewport
	def setViewport(self,x1,y1,x2,y2):
		if (x2<x1): x1,x2=x2,x1
		if (y2<y1): y1,y2=y2,y1

		W,H=self.getWidth(),self.getHeight()

		# fix aspect ratio
		if W>0 and H>0:
			assert(W>0 and H>0)
			w,cx =(x2-x1),x1+0.5*(x2-x1)
			h,cy =(y2-y1),y1+0.5*(y2-y1)
			if (w/W) > (h/H): 
				h=(w/W)*H 
			else: 
				w=(h/H)*W
			x1,y1=cx-w/2,cy-h/2
			x2,y2=cx+w/2,cy+h/2

		logger.info(f"setViewport {x1} {y1} {x2} {y2} W={W} H={H}")
		self.fig.x_range.start,self.fig.x_range.end=x1,x2
		self.fig.y_range.start,self.fig.y_range.end=y1,y2
		

	# renderPoints
	def renderPoints(self,points, size=20, color="red", marker="cross"):
		if self.points is not None: 
			self.fig.renderers.remove(self.points)
		self.points = self.fig.scatter(x=[p[0] for p in points], y=[p[1] for p in points], size=size, color=color, marker=marker)   
		assert self.points in self.fig.renderers


	# setImage
	def setImage(self, data, x1, y1, x2, y2):

		img=ConvertDataForRendering(data)
		dtype=img.dtype
 
		if self.dtype==dtype and self.color_mapper==self.color_bar.color_mapper:
			# current dtype is 'compatible' with the new image dtype, just change the source _data
			self.source_image.data={"image":[img], "x":[x1], "y":[y1], "dw":[x2-x1], "dh":[y2-y1]}
		else:
			# need to create a new one from scratch
			self.fig.renderers=[]
			self.source_image = bokeh.models.ColumnDataSource(data={"image":[img], "x":[x1], "y":[y1], "dw":[x2-x1], "dh":[y2-y1]})
			if img.dtype==np.uint32:	
				self.image_rgba=self.fig.image_rgba("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh") 
			else:
				self.img=self.fig.image("image", source=self.source_image, x="x", y="y", dw="dw", dh="dh", color_mapper=self.color_bar.color_mapper) 
			self.dtype=img.dtype
			self.color_mapper=self.color_bar.color_mapper
