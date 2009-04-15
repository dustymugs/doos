import sys
import threading
import hashlib
import os
import signal

from Queue import Queue
from datetime import datetime

# custom modules
from server import utils
from controller import runScript

#should only receive a job from the dispatcher when self.job is empty

#officeInstance inherits from Thread
class singleProcess (threading.Thread):
	'''
	This class is the controller for each thread.  It references a class which implements the finer control of the external process.
	It also wraps and forwards externally callable functions such as deathNotify and getPIDs, applying mutexes where appropriate.
	'''

	def __init__(self, threadNumber, server):
		threading.Thread.__init__(self, name="singleProcess" + threadNumber)
		self.threadId = threadNumber

		self.server = server
		self.log = server.log
		self.home = server.home

		self.ooScriptRunner = runScript.scriptRunner(self.threadId, self.home, self.server.waitMutex, self)
		self.myKidsMutex = threading.Lock() #prevents conflicts between getPIDs() and deathNotify()
		self.shuttingDown = False

	def run(self):
		'''
		The run function constantly grabs new jobs from the jobQueue until it receives the directory path "terminate", at which point it 
		shuts down.  Jobs are passed as the path to the input files ticketNumber.data and ticketNumber.args (everything up to the '.' is
		passed).
		'''
		while 1:
			dirpath = self.server.jobQueue.get(True) #block this thread's execution until it gets something from the queue

			#if dirpath is just 'terminate', then the server is telling the thread to shut down gracefully
			if dirpath == 'terminate':
				self.log('Thread ' + str(self.threadId) + ' exiting gracefully...')
				self.server.jobQueue.task_done()
				self.clear()
				break
			else:
				# parse out the ticket number
				(junk, ticketNumber) = dirpath.rsplit('/', 1) #the ticket number is what's at the end of the path to the input file

				#each element in jobDistribution is a tuple of ( ticketNumber, time recorded, extensionsGranted)
				self.server.watchdog.updateThread(self.threadId, ticket=ticketNumber, extensionsGranted=0)

				#jobs are passed as dirpath, the path to the ticket's input files e.g. "/doos/workspace/files/input/23424"
				#read the arguments from the .args file for this ticket
				file = open(dirpath + '.args', 'r')
				args = file.read()
				file.close()

				#parse the arguments
				args = utils.makeDictionary(args)

				#now write the time that the file was taken out of the queue
				file = open(self.home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')
				file.write('timeDequeued:' + datetime.now().isoformat() + "\n")
				file.close()

				#execution stage
				success = self.ooScriptRunner.execute(dirpath, args)

				#write the job's status to status.txt now that it's done
				file = open(self.home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')

				if success:
					file.write('timeCompleted:')
					self.log('Thread ' + self.threadId + ' successfully processed job ' + ticketNumber)
				else:
					file.write('timeFailed:')
					self.log('Thread ' + self.threadId + ' has abandoned job ' + ticketNumber, 'error\t')

				file.write( datetime.now().isoformat() + "\n" )
				file.close()

				#remove the input files now that we're done with them
				os.remove(dirpath + '.data') 
				os.remove(dirpath + '.args')

				self.server.jobQueue.task_done() #helps the queue keep track of how many jobs are still running
				self.server.watchdog.updateThread(self.threadId, ticket='ready', extensionsGranted=0)

	def deathNotify(self, deadKids):
		'''
		When one of the processes registered by this thread to the watchdog dies and is caught by the watchdog (through 
		SIGCHLD from the system), the watchdog will pass the list of dead processes to this function.  This function grabs 
		the myKidsMutex to block getPIDs() calls temporarily, and passes the dead kids notification on to the implemented 
		process handler.  It will then update the watchdog's process list for this thread.

		The function will do nothing if self.clear() has been run (and we are therefore shutting down).
		'''
		if not self.shuttingDown:
			self.myKidsMutex.acquire()
			newProcessList = self.ooScriptRunner.deathNotify(deadKids)
			self.myKidsMutex.release()

	def getPIDs(self):
		'''
		Returns a list of the process IDs which the implemented class wants watchdog to watch.
		If ANY of the watched processes dies, ALL of the thread's processes will be killed by
		the watchdog and deathNotify will be passed.

		If you're running a set of processes which has a lot of short-lived children, only list
		the main parent's pid in your implementation of this function

		PIDs are returned in the following format:
			["123", "4325", "2342"]
		'''
		#use the myKidsMutex so that deathNotify doesn't screw with this
		self.myKidsMutex.acquire()
		myKids = self.ooScriptRunner.getPIDs()
		self.myKidsMutex.release()
		return myKids

	def clear(self):
		'''
		Pre-destructor code to:
			break circular references between the watchdog and the thread
			kill child processes
		'''
		self.shuttingDown = True

		#get the PIDs of the processes associated with this thread
		pids = self.getPIDs()

		#and kill them all
		utils.kill([pids], self.server.waitMutex)

		self.server.watchdog.removeThread(self.threadId) #inform watchdog that this thread is shutting down
		self.ooScriptRunner.clear()
		self.server = None
