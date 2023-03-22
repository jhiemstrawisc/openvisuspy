
import numpy as np
import os,sys,logging,asyncio,time

logger = logging.getLogger(__name__)

# ///////////////////////////////////////////////
def IsPyodide():
	return "pyodide" in sys.modules

# ///////////////////////////////////////////////
def IsPanelServe():
	return "panel.command.serve" in sys.modules 

# ///////////////////////////////////////////////
def GetBackend():
	ret=os.environ.get("VISUS_BACKEND", "py" if IsPyodide() else "cpp")
	assert(ret=="cpp" or ret=="py")
	return ret

# ///////////////////////////////////////////////
async def SleepMsec(msec):
	await asyncio.sleep(msec/1000.0)

# ///////////////////////////////////////////////
def AddAsyncLoop(name, fn, msec):

	# do I need this?
	if False and not IsPyodide():
		loop = asyncio.get_event_loop()
		if loop is None:
			logger.info(f"Setting new event loop")
			loop=asyncio.new_event_loop() 
			asyncio.set_event_loop(loop)

	async def MyLoop():
		t1=time.time()
		while True:
			if (time.time()-t1)>5.0:
				logger.info(f"{name} is alive...")
				t1=time.time()
			try:
				await fn()
			except Exception as ex:
				logger.info(f"ERROR {fn} : {ex}")
			await SleepMsec(msec)

	return asyncio.create_task(MyLoop())			 


# ///////////////////////////////////////////////////////////////////
def EnsureFuture(coroutine):
	asyncio.ensure_future(coroutine)

# ///////////////////////////////////////////////////////////////////
def cbool(value):
    if isinstance(value,bool):
        return value

    if isinstance(value,int) or isinstance(value,float):
        return bool(value)

    if isinstance(value, str):
        return value.lower().strip() in ['true', '1']
    
    raise Exception("not supported")


# ///////////////////////////////////////////////////////////////////
def IsIterable(value):
	try:
		iter(value)
		return True
	except:
		return False

# ////////////////////////////////////////////////////////////////////////////////////////////////////////////
def Clamp(value,a,b):
	assert a<=b
	if value<a: value=a
	if value>b: value=b
	return value

# ///////////////////////////////////////////////////////////////////
def HumanSize(size):
	KiB,MiB,GiB,TiB=1024,1024*1024,1024*1024*1024,1024*1024*1024*1024
	if size>TiB: return "{:.2f}TiB".format(size/TiB) 
	if size>GiB: return "{:.2f}GiB".format(size/GiB) 
	if size>MiB: return "{:.2f}MiB".format(size/MiB) 
	if size>KiB: return "{:.2f}KiB".format(size/KiB) 
	return str(size)


# ////////////////////////////////////////////////////////////////
def SetupLogger(logger, output_stdout:bool=True, log_filename:str=None, logging_level=logging.INFO):

	logger.setLevel(logging_level)

	# stdout
	if output_stdout:
		handler=logging.StreamHandler()
		handler.setLevel(logging_level)

		handler.setFormatter(logging.Formatter(fmt=f"[%(asctime)s][%(levelname)s][%(name)s:%(lineno)d:%(funcName)s] %(message)s", datefmt="%H%M%S"))
		logger.addHandler(handler)
	
	# file
	if log_filename:
		os.makedirs(os.path.dirname(log_filename),exist_ok=True)
		handler=logging.FileHandler(log_filename)
		handler.setLevel(logging_level)
		handler.setFormatter(logging.Formatter(fmt=f"[%(asctime)s][%(levelname)s][%(name)s:%(lineno)d:%(funcName)s] %(message)s", datefmt="%H%M%S"))
		logger.addHandler(handler)


# ///////////////////////////////////////////////////
def SplitChannels(array):
	return [array[...,C] for C in range(array.shape[-1])]

# ///////////////////////////////////////////////////
def InterleaveChannels(v):
	N=len(v)
	if N==0:
		raise Exception("empty image")
	if N==1: 
		return v[0]
	else:
		ret=np.zeros(v[0].shape + (N,), dtype=v[0].dtype)
		for C in range(N): 
			ret[...,C]=v[C]
		return ret 


# ///////////////////////////////////////////////////
def ConvertDataForRendering(data, normalize_float=True):
    
	height,width=data.shape[0],data.shape[1]

	# typycal case
	if data.dtype==np.uint8:

		# (height,width)::uint8... grayscale, I will apply the colormap
		if len(data.shape)==2:
			Gray=data
			return Gray 

		# (height,depth,channel)
		if len(data.shape)!=3:
			raise Exception(f"Wrong dtype={data.dtype} shape={data.shape}")

		channels=SplitChannels(data)

		if len(channels)==1:
			Gray=channels[0]
			return Gray

		if len(channels)==2:
			G,A=channels
			return  InterleaveChannels([G,G,G,A]).view(dtype=np.uint32).reshape([height,width]) 
	
		elif len(channels)==3:
			R,G,B=channels
			A=np.full(channels[0].shape, 255, np.uint8)
			return  InterleaveChannels([R,G,B,A]).view(dtype=np.uint32).reshape([height,width]) 

		elif len(channels)==4:
			R,G,B,A=channels
			return InterleaveChannels([R,G,B,A]).view(dtype=np.uint32).reshape([height,width]) 
		
	else:

		# (height,depth) ... I will apply matplotlib colormap 
		if len(data.shape)==2:
			G=data.astype(np.float32)
			return G
		
		# (height,depth,channel)
		if len(data.shape)!=3:
			raise Exception(f"Wrong dtype={data.dtype} shape={data.shape}")  
	
		# convert all channels in float32
		channels=SplitChannels(data)
		channels=[channel.astype(np.float32) for channel in channels]

		if normalize_float:
			for C,channel in enumerate(channels):
				m,M=np.min(channel),np.max(channel)
				channels[C]=(channel-m)/(M-m)

		if len(channels)==1:
			G=channels[0]
			return G

		if len(channels)==2:
			G,A=channels
			return InterleaveChannels([G,G,G,A])
	
		elif len(channels)==3:
			R,G,B=channels
			A=np.full(channels[0].shape, 1.0, np.float32)
			return InterleaveChannels([R,G,B,A])

		elif len(channels)==4:
			R,G,B,A=channels
			return InterleaveChannels([R,G,B,A])
	
	raise Exception(f"Wrong dtype={data.dtype} shape={data.shape}") 