'''
doos: A multi-threaded server for running client-provided macros in OpenOffice.org
Copyright (C) 2008 - 2009  therudegesture and dustymugs

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, a copy is available at
http://www.gnu.org/licenses/gpl-3.0-standalone.html
'''

import select
import socket
import sys
import threading
import ConfigParser
from Queue import Queue
import datetime, time

# custom modules
from singleProcess import singleProcess
from requestHandler import requestHandler
from watchdog import watchdog

class Server:
	def __init__(self, CFG):
		self.CFG = CFG

		if CFG.has_section('net') and CFG.has_option('net', 'host'):
			self.host = CFG.get('net', 'host')
		else:
			self.host = '' #socket.getsockname()

		if CFG.has_section('net') and CFG.has_option('net', 'port'):
			self.port = int(CFG.get('net', 'port'))
		else:
			self.port = 8568

		#the maximum number of waiting socket connections
		if CFG.has_section('net') and CFG.has_option('net', 'backlog'):
			self.backlog = int(CFG.get('net', 'backlog'))
		else:
			self.backlog = 100

		if CFG.has_section('net') and CFG.has_option('net', 'socketBufferSize'):
			self.socketBufferSize = int(CFG.get('net', 'socketBufferSize'))
		else:
			self.socketBufferSize = 4096

		if CFG.has_section('all') and CFG.has_option('all', 'workspace'):
			self.home = CFG.get('all', 'workspace')
		else:
			print 'Value not provided for workspace.  Aborting...';
			sys.exit(1);

		self.logfile = open(self.home + 'logs/server.log', 'a')

		if CFG.has_section('server') and CFG.has_option('server', 'numSingleProcesses'):
			self.numSingleProcesses = int(CFG.get('server', 'numSingleProcesses'))
		else:
			self.numSingleProcesses = 1

		if CFG.has_section('net') and CFG.has_option('net', 'serverSocketRetry'):
			self.serverSocketRetry = int(CFG.get('net', 'serverSocketRetry'))
		else:
			self.serverSocketRetry = 15
			
		if CFG.has_section('net') and CFG.has_option('net', 'serverSelectTimeout'):
			self.serverSelectTimeout = int(CFG.get('net', 'serverSelectTimeout'))
		else:
			self.serverSelectTimeout = 30
			
		self.logMutex = threading.Lock()
		self.log("Starting server")

		self.server = None
		self.jobQueue = Queue()

		#this keeps track of which thread has which job
		self.singleProcesses = {}

		self.running = True
		self.input = []
		self.watchdog = watchdog(self)
		self.waitMutex = threading.Lock()

		self.log("Starting " + str(self.numSingleProcesses) + " singleProcess instances.")

		#Create numsingleProcesses singleProcess's, indexed by an id.
		for i in range(self.numSingleProcesses):
			i = str(i)
			self.log("Starting thread 'singleProcess" + i + "'.")
			self.watchdog.addThread(i)
			self.singleProcesses[i] = singleProcess( i, self)
			self.singleProcesses[i].start()

		self.log("Starting thread 'watchdog'.")
		self.watchdog.start()

	def log(self, message, level="information"):
		# Log message to the server's logfile, preceeded by a timestamp and a severity level
		timeLogged = datetime.datetime.now().isoformat()
		self.logMutex.acquire()
		self.logfile.write('[' + timeLogged + ']\t' + str(level) + '\t' + str(message) + "\n")
		self.logfile.flush() #be sure to flush the message out to the logfile
		self.logMutex.release()

	def terminate(self):
		self.log('Setting flag "Server.running" to false.')
		self.running = False

	def run(self):
		while True:
			try:
				self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				self.server.bind((self.host, self.port))
				self.server.listen(self.backlog)
				break
			except socket.error, (value, message):
				if self.serverSocketRetry > 0:
					self.log("Socket error. Retrying in 2 seconds...", "error\t")
					time.sleep(2)
					self.serverSocketRetry -= 2
				else:
					self.log("Could not open server listening socket: Connection attempts timed out.", "abort")
					self.server = None
					break
			except Exception, (message):
				self.log("Could not open server listening socket: " + str(message), "abort")
				self.server = None
				break

		if self.server is not None:
			self.log("Server listening on port " + str(self.port))
			self.log('Server ready to accept clients')

			#start the singleProcess threads
			self.input = [self.server]
			running = 1
			while self.running:
				#choose among the input sources which are ready to give data.  Choosing between stdin, the server socket, and established client connections
				inputready,outputready,exceptready = select.select(self.input,[],[], self.serverSelectTimeout)

				for s in inputready:
					if not running:
						break

					# handle the server socket (for when someone is trying to connect)
					elif s is self.server:
						try:
							client, address = self.server.accept()
							self.input.append(client)
							client.setblocking(0)
						except socket.error, (value, message):
							#do nothing--we've probably just connected without the client having sent any data
							self.log('Error connecting to client:\n' + str(value) + "\n" + str(message), 'error\t')

					#a connected client has sent data for us to process
					elif type(s) == type(self.server): #if it's not the server socket, but it is a socket,
						grabber = requestHandler (s, self)  #create a thread to handle the request
						self.input.remove ( s ) #tell the server thread to stop looking for input on this socket
						grabber.start()

			self.log('Closing Server.server socket...')
			self.server.close()

		#exiting gracefully; allow all threads to finish before closing
		# close all threads
		self.log("Queueing 'terminate' for each singleProcess instance.")
		for c in self.singleProcesses:
			self.jobQueue.put( 'terminate', True) #singleProcess threads will terminate when they process this as a job.  There's one for each thread.
		self.jobQueue.join()
		#the watchdog will shut itself down when all threads have removed themselves from its list.
		self.log('Server stopped')

	def __del__(self):
		self.logfile.close()
