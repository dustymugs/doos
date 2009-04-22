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

import os
import threading
import datetime, time

import utils

class watchdog(threading.Thread):
	'''
	This thread checks every *interval* seconds (usually 5 seconds) to make sure of the following:

		For the threads which have jobs:
			If they're still running after self.timeout and they haven't been using much CPU time, kill them.
				else if they're still running but are using a fair amount of CPU time, give them 1/2 of self.timeout longer to run.

		Have any processes died since the last time watchdog was awake?
			If so, inform the appropriate threads (which will then restart them)

	self.threads keeps track of what each thread is and is supposed to be up to.  Each threadId has a key.  Each element of 
	self.threads represents one thread, and is itself a dictionary with the following keys:

		"ticket": a string representing the ticket number of the job being worked on, or "ready" if the thread is idle
		"processes": a list of the strings, each representing a Process ID which was spawned by the thread
		"extensions granted": the number of times that the job has been given extra time over the default timeout
		"timestamp": the time the most recent job was accepted by the thread (approximately timeDequeued in status.txt)
		"cpu": the sum of the cpu usage samples taken for the current job

	self.threads is of the form:
		[
			"0": { "ticket":'2423528', "processes":["123", "124", "125"], "extensions granted":0, "timestamp":1219194339.800941, "cpu": 10.3 }, 
			"1": { "ticket":'171471', "processes":["588"], "extensions granted":1, "timestamp":1219194335.857452, "cpu": 15.3 }, 
			"2": { "ticket":'ready', "processes":["242", "243", "245"], "extensions granted":0, "timestamp":1219194339.800941, "cpu": 0.4 }
		] (etc.)

			where the index is the thread id, and parent and child are string representations of process IDs
			The PID of the parent process always goes first in the "processes" list.
			The purpose of differentiating the parent is so that utils.kill() can send SIGTERM
			to the parent and giving it an opportunity to bury its children.  Failing that, it'll send 
			SIGKILL to whoever is still alive among the parent and its children.
	'''

	def __init__(self, server):
		threading.Thread.__init__(self, name="watchdog")
		CFG = server.CFG

		 #the number of seconds for which watchdog sleeps after checking the threads
		if CFG.has_section('watchdog') and CFG.has_option('watchdog', 'interval'):
			self.interval = datetime.timedelta(seconds=int(CFG.get('watchdog', 'interval')))
		else:
			self.interval = datetime.timedelta(seconds=2)

		#the normal length of time a job has to complete before being killed
		if CFG.has_section('watchdog') and CFG.has_option('watchdog', 'jobTimeout'):
			self.jobTimeout = datetime.timedelta(seconds=int(CFG.get('watchdog', 'jobTimeout')))
		else:
			self.jobTimeout = datetime.timedelta(seconds=10)

		#maximum number of time extensions over the jobTimeout that can be given if the thread is still using the CPU
		if CFG.has_section('watchdog') and CFG.has_option('watchdog', 'maxExtensions'):
			self.maxExtensions = CFG.get('watchdog', 'maxExtensions')
		else:
			self.maxExtensions = 1

		#the minimum average of the percent of the CPU which a thread must be using to be kept alive past the jobTimeout
		if CFG.has_section('watchdog') and CFG.has_option('watchdog', 'minCPU'):
			self.minCPU = CFG.get('watchdog', 'minCPU')
		else:
			self.minCPU = 10.0

		self.threads = {} #information about the threads being watched over
		self.threadsMutex = threading.Lock()
		self.running = True
		self.readyToExit = False #this is for the main thread's wait() loop. When all children have been reaped, this will be True
		self.server = server
		self.log = server.log

	def run(self):
		# The main execution function for watchdog
		while not self.readyToExit:
			time.sleep(self.interval.seconds)

			#check to see if any children have died, and reap them if they have.  Then notify the parents.
			self.blackStork()
			#need to acquire a lock here for the threads list since hatching and dying threads can modify this list
			self.threadsMutex.acquire()

			if self.threads == {}: #then all threads have been removed and it's time to shut down
				self.clear()
			else:
				processes = utils.checkProcesses( self.threads, self.server.waitMutex )

				try:
					for threadId in self.threads.keys():
						#if this thread is processing a job, determine whether or not it's been running too long
						if not self.threads[threadId]['ticket'] is 'ready':
							#first add this interval's sample of the CPU usage
							self.threads[threadId]["cpu"] += processes[threadId][0]
							#if the job has been running longer than self.jobTimeout seconds
							if self.jobTimeout < ( datetime.datetime.now() - self.threads[threadId]["timestamp"] ):
								#if there haven't been too many extensions granted, and the average CPU usage has been at least self.minCPU
								if self.threads[threadId]["extensions granted"] < self.maxExtensions and \
										self.threads[threadId]["cpu"] / ( self.jobTimeout.seconds // self.interval.seconds ) > self.minCPU:
									self.threads[threadId]["extensions granted"] += 1 #note that another extension has been granted
									self.threads[threadId]["timestamp"] += self.jobTimeout / 2 #pretends that the job started 1/2 of jobTimeout later
								else:
									'''
									This job's time has run out.  Kill the processes and deathNotify singleProcess.
									Reset the timestamp and the extensions granted.
									this will not become an infinite time extension because singleProcess will give up 
									on a job after too many failures.
									'''
									self.log("Watchdog is killing job " + self.threads[threadId]["ticket"] + " in thread " + \
										threadId + " for taking too long.")
									self.threads[threadId]["extensions granted"] = 0
									self.threads[threadId]["timestamp"] = datetime.datetime.now()

									utils.kill(self.threads[threadId]["processes"], self.server.waitMutex)
									#restarting a thread takes so long that it makes sense to refresh information about the threads
									processes = utils.checkProcesses( self.threads, self.server.waitMutex )
				#in case removeThread() was called while watchdog was running
				except KeyError:
					pass
			#release the mutex so that runScript can deal with its dead child
			self.threadsMutex.release()

	def clear(self):
		self.readyToExit = True
		self.server = None
		self.log("Watchdog shutting down...")

	def blackStork(self):
		'''
		This function calls a non-blocking wait on the direct children of the server.
		Returns a list of process IDs which have died without having been wait()ed for
		Any call to subprocess or Popen which depends on the returned value of the process it starts
			must LOCK the server.waitMutex before starting the process.  This is because
			the exit status of a process can only be retrieved once, and without setting that mutex,
			this function may absorb the necessary information.
		This function is needed because when child processes terminate but aren't wait()ed for, they
			become Zombie processes which take up memory but don't do anything useful.
		'''
		#Handle dying children.
		#this loop's condition will be tested on init or when all of the children have died, be it because the server's shutting down
		#or because all child processes have crashed and none have yet been restarted
		deadChildren = []
		while True:
			self.server.waitMutex.acquire()

			try:
				pid, exit = os.waitpid(-1, os.WUNTRACED | os.WNOHANG) #look for the death of a direct child of this process
			except OSError, (value, message):
				if value == 10:
					pid = 0
				else:
					raise OSError(value, message)

			# waitMutex needs to be released before calling dropProcesses to prevent a deadlock
			# because otherwise this function would have both waitMutex and executionMutex(through
			# deathNotify(), and at the same time runScript.ooScriptRunner.execute() uses both the 
			# waitMutex and the executionMutex
			self.server.waitMutex.release()

			if pid == 0: break
			deadChildren.append( str(pid) )
			self.log("Child " + str(pid) + " has died.", 'error\t')

		if len(deadChildren) > 0:
			self.dropProcesses(deadChildren, True) #notify the watchdog that the process has died, which will then tell the thread

	def removeThread(self, threadId):
		'''
		Remove the specified thread from the list over which watchdog watches
		'''
		self.threadsMutex.acquire()

		try:
			del self.threads[threadId]
		except KeyError: #if that threadId doesn't exist in the dictionary
			self.log("watchdog failed to remove threadId '" + threadId + "' because it is not in its list.", 'error\t')
		except Exception, (message):
			self.log("watchdog failed to remove threadId '" + threadId + "': " + str(message), 'error\t' )
		else:
			self.log("watchdog removed thread " + threadId)

		self.threadsMutex.release()

	def addThread(self, threadId, processes=[], ticketNumber='ready'):
		'''
		add the thread to watchdog's list.
		Optionally include processes to watch over, and include the thread's status or which job it's working on.
		'''
		self.threadsMutex.acquire()
		self.threads[threadId] = {} #define a key for the thread in watchdog's list
		self.threadsMutex.release()

		self.log("watchdog added thread " + threadId)
		self.updateThread(threadId=threadId, processes=processes, ticket=ticketNumber, extensionsGranted=0)

	def updateThread(self, threadId, processes=None, ticket=None, extensionsGranted=None):
		'''
		Update watchdog's self.threads dictionary entry for thread *threadId*, 
		only changing variables that are passed in:
			processes for "processes", ticket for "ticket", extensionsGranted for "extensions granted"

		If a ticket is passed, reset the CPU usage sum and set the timestamp to right now
		'''
		self.threadsMutex.acquire()

		#only update the thread's status if the argument is not the keyword None
		if not ticket is None:
			self.threads[threadId]["ticket"] = ticket
			self.threads[threadId]["cpu"] = 0 #if there's a new ticket, reset the cpu usage sum
			self.threads[threadId]["timestamp"] = datetime.datetime.now() #and the timestamp

		#only update the processes list if the argument is not the keyword None
		if not processes is None:
			self.threads[threadId]["processes"] = processes

		if not extensionsGranted is None:
			self.threads[threadId]["extensions granted"] = extensionsGranted

		self.threadsMutex.release()

	def dropProcesses(self, processes, notifyThread=True):
		'''
		Stop watching these processes.  processes can be a string if it's a single process, or a list of strings.
		If notifyThread is True, the threads associated with each of the dropped processes will be notified that 
		they've been dropped (if the thread didn't call this itself, the process probably died and was taken by 
		the blackStork).
		'''
		#if it's a single string, make it a list
		if type(processes) == type( '' ):
			processes = [processes]

		#the list of dropped processes will be sent to the appropriate thread
		#dropped will store the dropped processes, grouped by threadId
		dropped = {}
		self.threadsMutex.acquire()

		#search through all of the processes in each thread to see if this process was being watched
		for threadId in self.threads.keys():
			for watched in self.threads[threadId]['processes']:
				if watched in processes:
					processes.remove(watched)
					self.threads[threadId]['processes'].remove(watched)
					if self.threads[threadId]['processes'] == None: #checkProcesses expects a list (possible empty) of strings; won't work with None
						self.threads[threadId]['processes'] = []

					if notifyThread:
						if not threadId in dropped:
							dropped[threadId] = []
						dropped[threadId].append(watched)

		self.threadsMutex.release()

		#if notifyThread is False, dropped will be empty
		for threadId in dropped:
			self.server.singleProcesses[threadId].deathNotify(dropped[threadId])
