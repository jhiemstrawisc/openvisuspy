
import os,sys,shutil
from datetime import datetime
from openvisuspy import SaveFile,LoadXML,SaveXML, LoadJSON,SaveJSON


# ///////////////////////////////////////////////////////////////////
def GenerateModVisusConfig(db, filename, group_name, group_filename):

	# save the include
	v=[f"""<dataset name='{row["group"]}/{row["name"]}' url='{row["dst"]}' group='{row["group"]}' convert_id='{row["id"]}' />""" for row in db.getConverted()]
	body="\n".join([f"<!-- file automatically generated {str(datetime.now())} -->"] + v + [""])
	SaveFile(group_filename,body)

	# make a backup copy of root visus.config
	timestamp=str(datetime.now().date()) + '_' + str(datetime.now().time()).replace(':', '.')
	shutil.copy(filename,filename+f".{timestamp}")

	# Open the file and read the contents 
	d=LoadXML(filename)

	datasets=d["visus"]["datasets"]
	if not "group" in datasets:
		datasets["group"]=[]

	if isinstance(datasets["group"],dict):
		datasets["group"]=[datasets["group"]]

	datasets["group"]=[it for it in datasets["group"] if it["@name"]!=group_name]

	datasets["group"].append({
		'@name': group_name,
		'include': {'@url': group_filename}
	})

	SaveXML(filename, d)


# ///////////////////////////////////////////////////////////////////
def GenerateDashboardConfig(filename, specs=None):

	if os.path.isfile(filename):
		config=LoadJSON(filename)
	else:
		config={"datasets": []}

	# add an item to the config
	if specs is not None:
		group_name     = specs["group"]
		dataset_name   = specs["name"]
		local_url      = specs["dst"]
		metadata       = specs["metadata"]
		remote_url     = specs["remote_url"]

		config["datasets"].append({
			"name" : f"{group_name}/{dataset_name}",
			"url" : remote_url,
			"urls": [
				{"id": "remote","url": remote_url},
				{"id": "local" ,"url": local_url}
			],
			"color-mapper-type":"log",
			"metadata" : metadata + [{
				'type':'json-object', 
				'filename': 'generated-nsdf-convert.json',  
				'object' : {k:str(v) for k,v in specs.items() if k!="metadata"}
			}]
		})

	SaveJSON(filename,config)