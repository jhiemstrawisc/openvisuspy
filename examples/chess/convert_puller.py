
import os,sys,glob,json,shutil,logging

from openvisuspy import LoadJSON

logger = logging.getLogger("nsdf-convert")

# ///////////////////////////////////////////////////////////////////
class PullEventsBaseClass:
	
	# constructor
	def __init__(self,db):
		self.db=db

# ///////////////////////////////////////////////////////////////////
class PullEventsFromLocalDirectory(PullEventsBaseClass):

	# constructor	
	def __init__(self,db, pattern):
		super().__init__(db)
		self.pattern=pattern

	# pull
	def pull(self):
		for filename in list(glob.glob(self.pattern)):
				try:
					specs=LoadJSON(filename)
					logger.info(f"json.loads('{filename}') ok")
				except Exception as ex:
					logger.info(f"json.loads('{filename}') failed {ex}")
					continue

				print(specs)
				self.db.pushPendingConvert(**specs)
				shutil.move(filename,filename + ".~pushed")

# ///////////////////////////////////////////////////////////////////
class PullEventsFromRabbitMq(PullEventsBaseClass):

	# constructor
	def __init__(self,db, url, queue):
		import pika
		super().__init__(db)
		self.queue=queue
		self.connection_in = pika.BlockingConnection(pika.URLParameters(url))
		self.channel_in = self.connection_in.channel()
		self.channel_in.queue_declare(queue=queue)


	# pull
	def pull(self):

			# add all the messages to the database
			# https://pika.readthedocs.io/en/stable/examples/blocking_consumer_generator.html
			for method_frame, properties, body in self.channel_in.consume(self.queue, auto_ack=False,inactivity_timeout=0.1):

				if method_frame is None:  break  # timeout
				body=body.decode("utf-8").strip()
				specs=json.loads(body)
				logger.info(f"PubSub received message from queue={self.queue} body=\n{json.dumps(specs,indent=2)} ")
				logger.info(f"Adding item top local db")
				db.pushPendingConvert(**specs)

				# important to do only here, I don't want to loose any message
				self.channel_in.basic_ack(delivery_tag=method_frame.delivery_tag) 

			 # from PICKA: When you escape out of the loop, be sure to call consumer.cancel() to return any unprocessed messages.			
			self.channel_in.cancel()


