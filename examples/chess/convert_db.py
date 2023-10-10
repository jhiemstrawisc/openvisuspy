import os,sys,logging,json
import sqlite3 
from datetime import datetime

logger = logging.getLogger("nsdf-convert")

# ///////////////////////////////////////////////////////////////////////
class ConvertDb:

	# constructor
	def __init__(self, db_filename):
		
		self.conn = sqlite3.connect(db_filename)
		self.conn.row_factory = sqlite3.Row
		self.conn.execute("""
		CREATE TABLE IF NOT EXISTS datasets (
			id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
			'group' TEXT NOT NULL, 
			name TEXT NOT NULL,
			src TEXT NOT NULL,
			dst TEXT NOT NULL,
			compression TEXT,
			arco TEXT,
			metadata TEXT,
			insert_time timestamp NOT NULL, 
			conversion_start timestep ,
			conversion_end   timestamp 
		)
		""")
		self.conn.commit()

	# close
	def close(self):
		self.conn.close()
		self.conn=None

	# pushPendingConvert
	def pushPendingConvert(self, group, name, src, dst, compression="zip", arco="modvisus", metadata=[]):
		# TODO: if multiple converters?
		self.conn.executemany("INSERT INTO datasets ('group', name, src, dst, compression, arco, metadata, insert_time) values(?,?,?,?,?,?,?,?)",[
			(group, name, src, dst, compression, arco, json.dumps(metadata), datetime.now())
		])
		self.conn.commit()

	# toDict
	def toDict(self, row):
		if row is None: return None
		ret={k:row[k] for k in row.keys()}
		ret["metadata"]=json.loads(ret["metadata"])
		return ret

	# popPendingConvert
	def popPendingConvert(self):
		data = self.conn.execute("SELECT * FROM datasets WHERE conversion_start is NULL AND conversion_end is NULL order by id ASC LIMIT 1")
		ret=self.toDict(data.fetchone())
		if ret is None: return None
		ret["conversion_start"]=str(datetime.now())
		data = self.conn.execute("UPDATE datasets SET conversion_start==? where id=?",(ret["conversion_start"],ret["id"], ))
		self.conn.commit()
		return ret

	# setConvertDone
	def setConvertDone(self, specs):
		specs["conversion_end"]=str(datetime.now())
		data = self.conn.execute("UPDATE datasets SET conversion_end==? where id=?",(specs["conversion_end"],specs["id"], ))
		self.conn.commit()

	# getRecords
	def getRecords(self, where):
		for it in self.conn.execute(f"SELECT * FROM datasets {where} ORDER BY id ASC"):
			yield self.toDict(it)

	# getRecordById
	def getRecordById(self,id):
		data=self.conn.execute("SELECT * FROM datasets WHERE id=?",[id])
		return self.toDict(data.fetchone()) 

	# getConverted
	def getConverted(self):
		for it in self.conn.execute("SELECT * FROM datasets WHERE conversion_end is not NULL ORDER BY id ASC"):
			yield self.toDict(it)

		