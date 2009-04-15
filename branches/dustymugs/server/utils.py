'''
Utility functions for doos and its components
TODO: find a way to get the logging function in here
'''

import time
import subprocess
import os
import signal
import datetime

def makeDictionary(argString):
	'''
	turn a string which was formatted like so: 
	key1=value1;key2=value2;key3;key4;key5=value5
	into a dictionary
	'''
	#split up the arguments if there are several, and put them into key/value pairs
	splitArgs = argString.split(";")
	args={} #args is now a dictionary

	for arg in splitArgs:
		arg = arg.split("=", 1)
		if len(arg) is 1: #for value-less arguments like ("terminate")
			args[ arg[0] ] = True #assign them the value of True
		else:
			args[ arg[0] ] = arg[1]

	return args

def checkProcesses(groups, waitMutex):
	'''
	Generate a dictionary of collective CPU usage for each thread's processes
	Expects a dictionary "groups" of the form:

		{
			1: { 'processes': ['132', '2133', '1231'] },
			2: { 'processes': ['34', '2435'] },
			0: { 'processes': ['345', '55', '345', '3455'] }
		}

		...where the key is the thread id according to singleProcess.py

	Returns a similar dictionary, but CPU usage is given as a percentage of total CPU time, followed by associated PIDs:

		{
			1: [ 22, ['132', '2133', '1231'] ],
			2: [ 12, ['34', '2435'] ],
			0: [ 1, ['345', '55', '345', '3455'] ]
		}

	This function has only been tested on Linux's ps (procps version 3.2.7)
	'''
	pidString = ""
	threads = {}
	ownerOf = {} #pairs a Process ID with the thread it belongs to

	for threadId in groups.keys():
		PIDs = groups[threadId]['processes']
		#start creating the hierarchy
		threads[threadId] = [ 0.0, PIDs ] #each thread has an entry of (CPU usage, process IDs)
		pidString += ",".join(PIDs) + ','
		for process in PIDs:
			ownerOf[process] = threadId

	pidString = pidString[:-1] #remove that trailing ','

	if len(pidString) > 0:
		#acquire the right to wait
		waitMutex.acquire()

		#output the PID and CPU usage of the processes in threadString
		ps = subprocess.Popen(("ps", "S", "--no-headers", "o", "pid,pcpu", "--pid", pidString), stdout=subprocess.PIPE)
		processStrings = ps.communicate()[0].split("\n") #make a list of strings with PID and CPU usage

		#release the wait mutex
		waitMutex.release()

		#now run through the result of ps and add each process's cpu usage to its thread's total
		for process in processStrings[:-1]: #the last item of processStrings will be '' so drop it
			pid, cpu =  process.split(None, 2)
			pid = pid.lstrip() #get rid of leading whitespace
			threads[ ownerOf[pid] ]  [0] += float(cpu) #adds to the cpu usage of that PID's thread

	return threads

def kill(drunkards, waitMutex, timeToDie=3.0):
	'''
	Kill the passed processes in the same way that people at Froggy's deal with drunkards at closing time:
		Politely ask the drunkard to leave by giving him SIGTERM, and assume that he'll have the good graces
			to take his clique with him.
		Give him 3 seconds to get out
		If he's still there after three seconds, kill him and his little friends with SIGKILL

	Expects a list of threads whose processes are to be killed, with the parent process id at the head of each list:
		[
			[ "2300", "2321", "3424" ],  #2300 is the parent process id of this thread
			[ "864", "8668", "3838" ],    #864 is the parent process id of this thread
			[ "483", "4383", "3483" ]    #483 is the parent process id of this thread
		]
	
	Or a single list of strings of said PIDs:
		[ "2300", "2321", "3424" ],  #2300 is the parent process id

	TODO: IMPORTANT: drop the use of ps in favor of waitpid() for the killed threads.  Don't want watchdog to catch and deal with them.
	'''
	#if it's a single list of strings, wrap it in another list
	if type(drunkards[0]) is type(""):
		drunkards = [drunkards]

	checkList = [] #this list will be join()'d and passed to ps as the PIDs to investigate

	#acquire the right to call wait().  Don't want anyone else intercepting these kills.
	waitMutex.acquire()

	for clique in drunkards:
		drunkard = clique[0] #the first member of each list is the parent process
		try:
			checkList.append(drunkard)
			os.kill ( int(drunkard), signal.SIGTERM ) #politely ask the drunkard to leave and take his friends with him
		except OSError, (value, message):
			if value == 3: #the drunkard has already left
				checkList.remove(drunkard) #if he's already gone, scratch him off your list
			else:
				#print "Unknown OSError while attempting to shutdown process " + drunkard + ": " + message + "\n"
				pass
		except Exception, (message):
			#print "Unknown exception while attempting to shutdown process " + drunkard + ": " + str(message) + "\n"
			pass
		finally:
			checkList += clique[1:]

	#now give them timeToDie seconds to get out
	judgmentDay = datetime.datetime.now() + datetime.timedelta(seconds=timeToDie)

	#keep checking around to see if the drunkards have left. The processes can run on for a long time, but
	#come judgmentDay, the sinning processes will be judged and shall perish.
	while datetime.datetime.now() < judgmentDay:
		#don't do all this if there are no drunks left to worry about
		if len(checkList) > 0:
			#if there are still some lingering drunks, blink and look again.
			time.sleep(0.25)
			for drunkard in list(checkList): #add the list() to make a copy of checkList, since we want to modify it
				try:
					pid, exitStatus = os.waitpid(int(drunkard), os.WNOHANG) #look for the death of a direct child of this process
					if str(pid) == drunkard:
						checkList.remove(drunkard) #this drunkard is gone, so we don't need to SIGKILL him
				except OSError, (value, message):
					if value == 10: #this means that this PID was not our child, so it was (probably) our grand-child and we can't kill it
						checkList.remove(drunkard)
						break
					else:
						raise OSError(value, message)

		'''
		#check to see if any drunkards are still lingering (by running ps and passing it the list of process IDs)
		ps = subprocess.Popen( ("ps", "--no-headers", "o", "pid", "--pid", ",".join(checkList) ), stdout=subprocess.PIPE)
		lingeringDrunkards = ps.communicate()[0].split("\n") #make a list of PIDs which are still alive
		'''

		#for drunkard in lingeringDrunkards[:-1]: #the last item of lingeringDrunkards = ''
		for drunkard in checkList:
			try:
				os.kill ( int(drunkard), signal.SIGTERM ) #murder the drunkard
				os.waitpid( int(drunkard), os.WNOHANG )
			except OSError, (value, message):
				if value == 3: #the drunkard has already left
					#print "Notice: process " + drunkard + " is already dead; no SIGKILL necessary.\n"
					pass
				else:
					#print "Unknown OSError while attempting to SIGKILL process " + drunkard + ": " + message + "\n"
					pass
			except Exception, (message):
				#print "Unknown exception while attempting to SIGKILL process " + drunkard + ": " + str(message) + "\n"
				pass

	#release the wait mutex
	waitMutex.release()
