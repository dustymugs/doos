import os, shutil
import socket
import threading
import random
import hashlib
import datetime

import utils
from jobStatus import jobStatus

def formatResponse(response):
	m = hashlib.sha1()
	m.update(response)
	fr = str(m.hexdigest()) + '|' + response
	return (str(len(fr)) + '|' + fr)

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
					self.client.sendall(formatResponse("[ERROR] Checksum failed."))
				finally:
					raise Exception("Checksum failed! ")

			argString, data = data.split('::file start::', 1)

			#convert argString into a key-value dictionary
			args = utils.makeDictionary(argString)

			#guard against "terminate=false"
			if args.has_key('terminate') and args['terminate']:
				try:
					self.client.sendall(formatResponse("[OK]"))
				finally:
					self.log("Received shutdown command from '" + self.remoteHostName + "'.")
					self.server.terminate() #tell the server to shut down all threads

			#if they want to put it in the queue, dump the data to a file and enqueue
			elif args.has_key('prepareJob') and args['prepareJob'] is True:
				self.prepareJob(argString, data)

			#if they want status or they want the job
			elif ( (args.has_key('statusJob') and args['statusJob']) or (args.has_key('returnJob') and args['returnJob']) ) and args.has_key('ticket'):
				logfile, status = self.statusJob(args['ticket']) #get the file containing the job's status

				if status == jobStatus.notFound:
					self.client.sendall(formatResponse("[ERROR] Unknown Ticket: " + args['ticket'] + '.'))
					self.log("Sent 'ticket not found' for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.", 'error\t')
				elif (args.has_key('returnJob') and args['returnJob']) and status == jobStatus.done:
					#this function handles its own logging.
					self.returnJob( args['ticket'] )
				else:
					self.client.sendall(formatResponse("[OK] " + jobStatus.asText(status)))
					self.log("Sent status for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.")

			# command to delete output files of job from files/output
			# TODO: have command remove job from queue if job not processed yet
			elif (args.has_key('deleteJob') and args['deleteJob']) and args.has_key('ticket'):
				#this function handles its own logging.
				self.deleteJob(args['ticket'])
			else:
				self.client.sendall(formatResponse("[ERROR] Unknown command."))

		except socket.error, (message):
			self.log("Socket error for host '" + self.remoteHostName + "': " + str(message), "error\t")
		except Exception, (message):
			self.log("Unknown error for host '" + self.remoteHostName + "': " + str(message), "error\t")
		finally:
			#now close the connection
			self.client.close()

	# delete the output directory of the job ticket
	# TODO: have command remove job from queue if job not processed yet
	def deleteJob(self, ticket):
		deleteFlag = True

		# delete output directory of job ticket
		if os.path.exists(self.home + 'files/output/' + ticket):
			try:
				shutil.rmtree(self.home + 'files/output/' + ticket)
				self.log('Directory deleted for ticket ' + ticket + ' in path: ' + self.home + 'files/output/' + ticket)
			except Exception:
				self.log('Failure to delete directory for ticket ' + ticket + ' in path: ' + self.home + 'files/output/' + ticket, "error\t")
				deleteFlag = False
		else:
			self.log('Directory not found for ticket ' + ticket + ' in path: ' + self.home + 'files/output/' + ticket)

		# delete was completely successful
		if deleteFlag:
			self.client.sendall(formatResponse('[OK]'))
		# delete failed somewhere
		else:
			self.client.sendall(formatResponse('[ERROR] Error while attempt to delete contents for Ticket: ' + ticket + '.'))

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
					self.client.sendall(formatResponse('[ERROR] Unable to read all the output files of Ticket: ' + ticket + '.'))
				except Exception, (message):
					self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )
		except Exception, (message):
			self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )

		#So now we have the data (or failure).  Let's send the data back to the client.
		try:
			if isZip is not None:
				response = []
				for file in data:
					response.append('::file start::' + file[0] + '::file content::' + file[1] + '::file end::')
				self.client.sendall(formatResponse('[OK] ' + ''.join(response)))
		except socket.error, (message):
			self.log("Socket error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
		except Exception, (message):
			self.log("Unknown error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
		else:
			self.log("Successfully sent output for ticket '" + ticket + "' to '" + self.remoteHostName + "'.")

	def statusJob(self, ticket):
		try:
			file = open(self.home + "files/output/" + ticket + "/status.txt")
			logfile = file.read()
			file.close()
		except IOError, (value, message): #if the file is not found, the ticket doesn't exist.
			if value == 2:
				return "Ticket not found.", jobStatus.notFound
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
		# if the ticket already exists, keep generating a random ticket until an available one is found
		# keep checking the output folder too because this filename will be the unique ticket number, and
		# if there's a file there, that ticket is in the system (and waiting for some client to come claim it)
		randgen = random.Random()
		randgen.seed()
		ticket = str( randgen.randint(self.minTicketNumber, self.maxTicketNumber) )

		while os.path.exists(self.home + 'files/input/' + ticket) \
				or os.path.exists(self.home + 'files/output/' + ticket):
			ticket = str( randgen.randint(self.minTicketNumber, self.maxTicketNumber) )

		#path to the input dir
		dirpath = self.home + 'files/input/' + ticket + '/'
		os.mkdir(dirpath);

		# write the files to disk
		i = 0
		for x in data.split('::file start::'):
			x = x.rstrip('::file end::')
			filename, filecontent = x.split('::file content::', 1)

			# file 0 is always considered the main script file
			if i == 0: filename = 'main.script'

			if len(filename) < 1:
				self.client.sendall(formatResponse('[ERROR] Skipping unnamed file #' + i + ' of Ticket:' + ticket + '.'))
				self.log('File #' + i + ' of Job ' + ticket + ' does not have a name.  Skipping...')
				continue

			file = open(dirpath + filename, 'w')
			file.write(filecontent) #save the data
			file.close()

			i += 1

		#now write arguments to the handler for this command to a file
		file = open(dirpath + ticket + '.args', 'w')
		file.write(argString)
		file.close()

		#now create a directory for the job status file status.txt to be stored
		os.mkdir(self.home + 'files/output/' + ticket)
		file = open(self.home + 'files/output/' + ticket + '/status.txt', 'w')

		#log the date and time
		file.write('timeEntered:' + datetime.datetime.now().isoformat() + "\n")
		file.close()

		#finally, put the data into the queue
		self.server.jobQueue.put( dirpath, True )
		self.client.sendall(formatResponse("[OK] Ticket:" + ticket))
		self.log("Job '" + ticket + "' entered into queue.  Received from '" + self.remoteHostName + "'.")
