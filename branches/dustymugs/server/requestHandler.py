import os
import socket
import threading
import random
import hashlib
import datetime

import utils

class requestHandler(threading.Thread):
	def __init__(self, client, server):
		threading.Thread.__init__(self, name="requestHandler")
		self.client = client
		self.socketBufferSize = server.socketBufferSize

		CFG = server.CFG
		self.server = server
		self.log = self.server.log
		self.home = self.server.home

		client.setblocking(1)

		if CFG.has_section('request') and CFG.has_option('request', 'uploadTimeout'):
			client.settimeout(float(CFG.get('request', 'uploadTimeout')))
		else:
			client.settimeout(60.0)

		if CFG.has_section('request') and CFG.has_option('request', 'minTicketNumber'):
			self.minTicketNumber = int(CFG.get('request', 'minTicketNumber'))
		else:
			self.minTicketNumber = 0

		if CFG.has_section('request') and CFG.has_option('request', 'maxTicketNumber'):
			self.maxTicketNumber = int(CFG.get('request', 'maxTicketNumber'))
		else:
			self.maxTicketNumber = 15999999

		#try to find the remote machine's IP address
		try:
			self.remoteHostName = str( self.client.getpeername() )
		except Exception, (message):
			self.remoteHostName = "-system does not support getpeername()-"

	def run(self):
		try:
			self.log("Client connected from " + self.remoteHostName)
			data_chunks = [] #we're just concatenating the chunks of data received, but this is faster than string concatenation
			buf = self.client.recv(self.socketBufferSize)
			bytesExpected = None
			bytesGotten = 0

			while True: #the first part of the message, up to '|', is the length of the transmission.  Keep going till it's been exceeded
				if buf == '':
					raise socket.error("Socket has been broken before transmission completed. It probably failed.")
				data_chunks.append(buf)
				#find out how many bytes will be sent
				if bytesExpected is None:  #if we still haven't determined the number of bytes to expect
					buf = "".join(data_chunks) #in case the bytesExpected number was in another buffering, join whatever we've got
					i = buf.find("|")  #fields are delimited by | like so: bytesExpected|checkSum|argString|data
															#args is structred thus: "key1=value1;key2=value2;key3;key4;key5=value5"  etc
					if i is not -1:  #if | is found, then we have the bytesExpected
						bytesExpected = int(buf[:i])  #bytesExpected is the string from the beginning until the |
						data_chunks = [ buf[i+1:] ]  #we probably have more than just bytesExpected in the buffer, so store that data
						bytesGotten = len( data_chunks[0] )

				#if we're still determining the number of bytes to expect or we're still downloading the file,
				if bytesExpected is None or bytesGotten < bytesExpected:
					buf = self.client.recv(self.socketBufferSize)  #get more data
				else:
					break  #otherwise we're done.

			#data_chunks is a list of chunks of the data.  Join them together.
			data = "".join(data_chunks)
			checksum, data = data.split('|', 1) #pull out the checksum from the data

			#get the sha1 hash for checksumming
			m = hashlib.sha1()
			m.update(data)
			if (m.hexdigest() != checksum):
				try:
					self.client.sendall( "Checksum failed!" )
				finally:
					raise Exception("Checksum failed! ")

			argString, data = data.split('::file start::', 1)

			#convert argString into a key-value dictionary
			args = utils.makeDictionary(argString)

			if args.has_key('terminate') and args['terminate']: #guard against "terminate=false"
				try:
					self.client.sendall( "shutting down...\n" )
				finally:
					self.log("Received shutdown command from '" + self.remoteHostName + "'.")
					self.server.terminate() #tell the server to shut down all threads

			#if they want to put it in the queue, dump the data to a file and enqueue
			elif args.has_key('prepareJob') and args['prepareJob'] is True:
				self.prepareJob(argString, data)

			#if they want status or they want the job
			elif ( (args.has_key('stat') and args['stat']) or (args.has_key('returnJob') and args['returnJob']) ) and args.has_key('ticket'):
				logfile, status = self.stat(args['ticket']) #get the file containing the job's status

				if status == jobStatus.notFound:
					self.client.sendall( "STATUS " + str(status) + ": " + str(logfile) )
					self.log("Sent 'ticket not found' for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.", 'error\t')
				elif (args.has_key('returnJob') and args['returnJob']) and status == jobStatus.done:
					#this function handles its own logging.
					self.returnJob( args['ticket'] )
				else:
					self.client.sendall(logfile)
					self.log("Sent status for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.")
			else:
				self.client.sendall("STATUS " + jobStatus.error + ": Unknown command\n")

		except socket.error, (message):
			self.log("Socket error for host '" + self.remoteHostName + "': " + str(message), "error\t" )
		except Exception, (message):
			self.log("Unknown error for host '" + self.remoteHostName + "': " + str(message), 'error\t')
		finally:
			#now close the connection
			self.client.close()

	def returnJob(self, ticket):
		'''
		Send the completed job back to the client.  First look for files.zip, and if that
		doesn't exist look for the folder "files" and send its contents.
		data is stored as follows: [ (filename, data) ]
		'''
		isZip = None #start off assuming that zipping the output didn't work
		try:
			file = open(self.home + "files/output/" + ticket + "/files.zip")
			data = [ ('files.zip', file.read()) ]
			file.close()
			isZip = True
		except IOError, (value, message):
			#if the file is not found, the ticket doesn't exist.
			#zipping the output probably failed, meaning we probably have a HUGE file/set of files
			#Either that, or there was some unknown IO error.
			#Now we're going to try to read all of the files and load them
			#into data.
			try:
				data = []
				absoluteRoot = self.home + 'files/output/' + ticket + '/files/'
				for root, dirs, files in os.walk(self.home + 'files/output/' + ticket + '/files/'):
					for filename in files:
						#find relative root for the file's path
						(junk, relativeRoot) = root.split(absoluteRoot, 1)
						file = open(relativeRoot + filename)
						data.append( (relativeRoot + filename, file.read()) )
						file.close()
				isZip = False #mark that the output is a number of files, not just a single zip file

			#if we couldn't read all of the files
			except Exception, (message):
				try:
					self.client.sendall('STATUS ' + str(jobStatus.error) + ": " + str(message))
				except Exception, (message):
					self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )
		except Exception, (message):
			self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )

		#So now we have the data (or failure).  Let's send the data back to the client.
		try:
			if isZip is not None:
				for file in data:
					self.client.sendall( file[0] + "::file start::" + file[1] + "::fileEnd")
		except socket.error, (message):
			self.log("Socket error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
		except Exception, (message):
			self.log("Unknown error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
		else:
			self.log("Successfully sent output for ticket '" + ticket + "' to '" + self.remoteHostName + "'.")

	def stat(self, ticket):
		try:
			file = open(self.home + "files/output/" + ticket + "/status.txt")
			logfile = file.read()
			file.close()
		except IOError, (value, message): #if the file is not found, the ticket doesn't exist.
			if value == 2:
				return "Ticket not found.\n", jobStatus.notFound
			else:
				return str(message), jobStatus.error
		except Exception, (message):
			return "Unknown Error: " + str(message), jobStatus.error

		if logfile.find('timeCompleted:') >= 0:
			return logfile, jobStatus.done
		elif logfile.find('timeFailed:') >= 0:
			return logfile, jobStatus.error
		elif logfile.find('timeDequeued:') >= 0:
			return logfile, jobStatus.dequeued
		else:
			return logfile, jobStatus.enqueued

	def prepareJob(self, argString, data):
		#if the file already exists, keep generating a random filename until an available one is found
		#keep checking the output folder too because this filename will be the unique ticket number, and
		#if there's a file there, that ticket is in the system (and waiting for some client to come claim it)
		randgen = random.Random()
		randgen.seed()
		filename = str( randgen.randint(self.minTicketNumber, self.maxTicketNumber) )

		while os.path.exists(self.home + 'files/input/' + filename + '.data') \
				or os.path.exists(self.home + 'files/output/' + filename):
			filename = str( randgen.randint(self.minTicketNumber, self.maxTicketNumber) )

		#path to the input file
		dirpath = self.home + 'files/input/' + filename
		file = open(dirpath + '.data', 'w')
		file.write( data ) #save the data
		file.close()

		#now write arguments to the handler for this command to a file
		file = open(dirpath + '.args', 'w')
		file.write(argString)
		file.close()

		#now create a directory for the job status file status.txt to be stored
		os.mkdir(self.home + 'files/output/' + filename)
		file = open(self.home + 'files/output/' + filename + '/status.txt', 'w')

		#log the date and time
		file.write('timeEntered:' + datetime.datetime.now().isoformat() + "\n")
		file.close()

		#finally, put the data into the queue
		self.server.jobQueue.put( dirpath, True )
		self.client.sendall( "transmission ok\nticket number:" + filename + "\n")
		self.log("Job '" + filename + "' entered into queue.  Received from '" + self.remoteHostName + "'.")
