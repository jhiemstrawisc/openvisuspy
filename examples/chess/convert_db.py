import json
import logging
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
				conversion_start timestamp,
				conversion_end   timestamp,
				error_msg        TEXT
		)
		""")	
		self.conn.commit()

	# close
	def close(self):
		self.conn.close()
		self.conn = None


	# toDict
	def toDict(self, row):
		if row is None: return None
		ret = {k: row[k] for k in row.keys()}
		if "metadata" in ret:
			ret["metadata"] = json.loads(ret["metadata"])
		return ret

	# getRecordById
	def getRecordById(self, id):
		data = self.conn.execute("SELECT * FROM datasets WHERE id=?", [id])
		return self.toDict(data.fetchone())

	# pushPending
	def pushPending(self, group, name, src, dst, compression="zip", arco="8mb", metadata=[]):
			# TODO: if multiple converters?
			self.conn.executemany("INSERT INTO datasets ('group', name, src, dst, compression, arco, metadata) values(?,?,?,?,?,?,?)",
					[(group, name, src, dst, compression, arco, json.dumps(metadata))])
			self.conn.commit()

	# popPending
	def popPending(self):
		data=self.conn.execute(f"SELECT * FROM datasets WHERE conversion_start IS NULL ORDER BY id ASC LIMIT 1")
		ret=self.toDict(data.fetchone())
		if ret is None: return None 
		ret["conversion_start"] = str(datetime.now())
		self.conn.execute("UPDATE datasets SET conversion_start=? WHERE id=?", [ret["conversion_start"], ret["id"]])
		self.conn.commit()
		return ret

	# markDone (could be with an error_msg or not)
	def markDone(self, specs, error_msg=None):
		specs["conversion_end"] = str(datetime.now())
		if error_msg:
			self.conn.execute("UPDATE datasets set conversion_end=?, error_msg=? WHERE id=?", [specs["conversion_end"], error_msg , specs["id"]])
		else:
			self.conn.execute("UPDATE datasets set conversion_end=? WHERE id=?", [specs["conversion_end"], specs["id"]])
		self.conn.commit()

	# getRunning
	def getRunning(self):
			for it in self.conn.execute(f"SELECT * from datasets WHERE conversion_start IS NOT NULL AND conversion_end IS NULL"):
					yield self.toDict(it)

	# getConverted (returns only the ones without errors)
	def getConverted(self):
			for it in self.conn.execute(f"SELECT * FROM datasets WHERE conversion_end IS NOT NULL AND error_msg IS NULL ORDER BY id ASC"):
					yield self.toDict(it)

