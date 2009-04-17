'''
This is the class which controls OpenOffice.  You can see from singleProcess.py which functions need to be implemented if you want to write 
a class like this for another program.

TODO:
	When a thread is launched, be sure to nuke the output folder in case any residual files are chilling there.

	MAJOR SECURITY FLAW:  MUST PREVENT STARBASIC SHELL COMMAND FROM RUNNING!  It's available to OO macros
'''

import subprocess
import time
import datetime
import os
import shutil
import zipfile
import threading

# OpenOffice.org modules
import uno
from com.sun.star.beans import PropertyValue

# custom modules
from server import utils

class scriptRunner:
	def __init__(self, instanceId, homeDir, waitMutex, singleProcess):
		CFG = singleProcess.server.CFG

		self.instanceId = instanceId
		self.basePath = homeDir
		self.home = homeDir + "home" + str(instanceId) + '/'
		self.shuttingDown = False
		self.waitMutex = waitMutex
		self.executionMutex = threading.Lock()

		if CFG.has_section('runscript') and CFG.has_option('runscript', 'maxDispatchAttempts'):
			self.maxDispatchAttempts = int(CFG.get('runscript', 'maxDispatchAttempts'))
		else:
			self.maxDispatchAttempts = 2

		self.singleProcess = singleProcess
		self.log = singleProcess.server.log

		self.startOO()

	def startOO(self):
		#acquire the right to read from subprocesses
		#(even opening them through subprocess can cause a deadlock if two happen simultaneously)
		self.waitMutex.acquire()

		#create a new OpenOffice process and have it listen on a pipe
		self.childOffice = \
			subprocess.Popen( ('/opt/openoffice.org2.4/program/soffice', "-accept=pipe,name=doosPipe" + str(self.instanceId) + ";urp;", "-headless", "-nofirststartwizard"), \
				env={ "PATH": os.environ["PATH"], \
				"HOME": self.home } ) #we need to have several 'homes' to have
															#several OO instances running

		time.sleep(2.5)

		#OOo spawns a child process which we'll have to look out for.
		#now get the child process which has been spawned (need to kill -9 it in case anything goes wrong)
		self.grandchildren = []

		ps = subprocess.Popen(("ps", "--no-headers", "--ppid", str(self.childOffice.pid), "o", "pid"), \
			env={ "PATH": os.environ["PATH"]}, stdout=subprocess.PIPE)
		psOutput = ps.communicate()[0]

		#release the wait mutex
		self.waitMutex.release()

		for child in psOutput.split("\n")[:-1]: #the last element will be '' so drop it
			self.grandchildren.append(child.lstrip()) #needs to be a string rather than an int. Remove leading whitespace.

		#inform the watchdog of the new process ids
		if not self.singleProcess is None:
			self.singleProcess.server.watchdog.updateThread( self.instanceId, processes=self.getPIDs() )

		# get the uno component context from the PyUNO runtime
		localContext = uno.getComponentContext()

		# create the UnoUrlResolver
		self.resolver = localContext.ServiceManager.createInstanceWithContext(
			"com.sun.star.bridge.UnoUrlResolver", localContext )

		self.log("Done initializing OpenOffice for thread " + self.instanceId)

	def deathNotify(self, deadChildren):
		'''
		Called when the watchdog detects the death of the child office process.  This function waits until any pending job's execute()
		procedure is finished before restarting Open Office.
		self.execute() will determine whether or not the OOo instance crashed during the job, so deathNotify competes with execute() for
		the executionMutex.
		We only want to kill the PIDs active at the time deathNotify is run, and we only do that if one of the dead children is in the 
		family tree returned by self.getPIDs().  This is because deathNotify may come late, and if execute() has already restarted OO, 
		self.getPIDs() will return the new PIDs (we don't want to end up killing the new processes).
		'''
		familyTree = self.getPIDs() #get the current PIDs BEFORE waiting for the executionMutex.

		# we only want to restart if the reported dead child is still one we care about,
		# since execute() can restart the office instance on its own if it sees that the instance is dead.
		for deadbaby in deadChildren:
			if deadbaby in familyTree:
				self.executionMutex.acquire()
				self.log("Thread " + self.instanceId + "'s OpenOffice instance has died. Restarting it.", 'error\t')
				utils.kill( familyTree, self.waitMutex )
				self.startOO()
				self.executionMutex.release()

				break

	def getPIDs(self):
		'''
		Returns string representations of the PIDs OpenOffice instance spawned by this thread and any direct children that instance may have.
		'''
		return [str(self.childOffice.pid)] + self.grandchildren

	def execute(self, dirpath, args):
		'''
		Create a folder in this thread's home directory/output named after the ticket number of the current job.  This folder will contain
			any output files produced by the macro.  Search through the macro file and replace any instances of <<OUTDIR>> with the place
			we want the script to send output, which is the ticket folder we created.

		Grab the script located at dirpath, then connect to OpenOffice and run it.
		When done, move the folder we created to the program folder/files/output
		'''
		(junk, ticketNumber) = dirpath.rsplit('/', 1) #the ticket number is what's at the end of the path to the input file
		ticketNumber = str(ticketNumber)

		if not args.has_key('initFunc'):
			self.log( "Thread " + self.instanceId + " says: initFunc was not defined by client for ticket " + ticketNumber, 'error\t' )
			return false

		dirpath += '.data' #add .data to the end of the ticket number to get the macro's filename
		file = open(dirpath, 'r+') #open the passed macro

		# replace placeholder <<OUTDIR>> with worker's output location for ticket
		pathCorrected = file.read().replace('<<OUTDIR>>', self.home + 'output/' + ticketNumber + '/')

		# replace placeholder <<INDIR>> with global file input location for ticket
		pathCorrected = pathCorrected.replace('<<INDIR>>', self.basePath + 'files/input/' + ticketNumber + '/')

		# replace placeholder <<TEMPLATEDIR>> with global template path
		pathCorrected = pathCorrected.replace('<<TEMPLATEDIR>>', self.basePath + 'templates/')

		file.truncate(0) #to make sure we overwrite the file
		file.write(pathCorrected)
		file.close()

		executionSuccess = False
		#make two attempts at execution
		i = 1
		while (i <= self.maxDispatchAttempts):
			#prevent OO from being restarted by anyone else
			self.executionMutex.acquire()
			try:
				# connect to the running office
				self.ctx = self.resolver.resolve( "uno:pipe,name=doosPipe" + str(self.instanceId) + ";urp;StarOffice.ComponentContext" )

				# get the central desktop object
				self.desktop = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.Desktop",self.ctx)

				self.dispatchHelper = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.DispatchHelper", self.ctx )

				properties = []
				p = PropertyValue()
				p.Name = "junk"
				p.Value = 'in the trunk'
				properties.append(p)
				properties = tuple(properties)

				self.dispatchHelper.executeDispatch(self.desktop, 'macro:///AutoOOo.OOoCore.runScript(' + dirpath + ',' \
					+ args["initFunc"] + ')', "", 0, properties)

				# As quoted from the PyUno tutorial:
				#		Do a nasty thing before exiting the python process. In case the
				# 	last call is a oneway call (e.g. see idl-spec of insertString),
				# 	it must be forced out of the remote-bridge caches before python
				# 	exits the process. Otherwise, the oneway call may or may not reach
				# 	the target object.
				#
				# I do this here by calling a cheap synchronous call (getPropertyValue).
				self.ctx.ServiceManager

				self.log('Thread ' + self.instanceId + "'s OpenOffice is finished with job " + ticketNumber + '.  Now packaging...')

			#if OpenOffice crashed
			except Exception, (message):
				self.log("Open Office crashed for thread " + self.instanceId + " (message: " + str(message) + \
					") during execution of job number " + \
					ticketNumber + ".  " + str(self.maxDispatchAttempts - i) + " attempt(s) remaining before job is abandoned.\n", 'error\t')

				#only the PIDs which this iteration of the loop started with can be returned by getPIDs, because
				#execute() has the executionMutex, which is necessary for deathNotify() to restart OO.
				utils.kill( self.getPIDs(), self.waitMutex )
				self.startOO()
				i += 1

				#if OO died because watchdog killed it, watchdog is probably in runScript.deathNotify(), which is waiting for
				#executionMutex. Give it a chance to complete its calls and start monitoring again before re-acquiring the mutex.
				self.executionMutex.release()
				continue

			#else if there was no exception....
			else:
				#We're done with the macro.  Now try to zip the file.
				try:
					absoluteRoot = self.home + 'output/' + ticketNumber
					zip = zipfile.ZipFile(self.home + 'output/' + ticketNumber + '.zip', 'w', zipfile.ZIP_DEFLATED, True)

					for root, dirs, files in os.walk(absoluteRoot):
						for filename in files:
							#find relative root for representation in the zip file
							(junk, relativeRoot) = root.split(absoluteRoot, 1)

							zip.write("/".join([root,filename]), relativeRoot + filename)

					#if the zip was successful, move it to the server-wide output directory, [self.basePath]/files/output/[ticketNumber]/files.zip
					shutil.move(self.home + 'output/' + ticketNumber + '.zip', self.basePath + 'files/output/' + ticketNumber + '/files.zip')

				except Exception, (message):
					self.log("Thread " + self.instanceId + " encountered an error while writing the zip file for ticket " + \
						ticketNumber + ":\n" + str(message) + "\nMoving output folder instead.\n", 'error\t')

					#move the output directory to the server-wide output directory, [self.basePath]/files/output/[ticketNumber]/files
					shutil.move(self.home + 'output/' + ticketNumber, self.basePath + 'files/output/' + ticketNumber + '/files')
				# remove ticketNumber directory from worker's output directory
				finally:
					try:
						shutil.rmtree(self.home + 'output/' + ticketNumber)
					except Exception:
						self.log("Unable to remove directory: " + self.home + 'output/' + ticketNumber)

			executionSuccess = True

			#we won't get here if the job failed too many times because of the continue statement, so we don't need to worry about
			self.executionMutex.release() #releasing the lock when it isn't locked.

			break #if we made it this far, Open Office didn't crash, so we don't need to re-try.

		return executionSuccess

	def clear(self):
		self.waitMutex = None
		self.singleProcess = None

if __name__ == '__main__':
	juno = scriptRunner(2)
	juno.execute('this was a triumph', 321)
