#!/usr/bin/env python

"""
A process management server that uses threads to handle multiple jobs and clients at a time.
Entering any line of input at the terminal will exit the server.

When a client sends a job, he is assigned a ticket number which uniquely identifies the job in the system.
The input sent by the client is stored in homeDirectories/input/**ticket number**
When the job processing is finished, the job is stored in homeDirectories/output/**ticket number**

The protocol for any client request is this:

number of bytes following the pipe|checksum of everything following the pipe|arguments::file start::fileContents
( "::file start::" is a token )
The arguments string coming from the client should be formatted as follows:
	key1=value1;key2=value2;key3;key4;key5=value5  (etc)

When a client requests a ticket, the system searches the output folder for the ticket as a filename and returns the file if found.
	If that file is not found, but it is found in input/, then the server responds that the job is still being processed
	if that file is not found in either folder, the server replies that the ticket id is unknown
"""
'''
TODO:
	Fix exception handling with socket events
	If you restart a server, you'll get "Could not start up, socket in use."  Figure out how to make it work, or just quit.
	On server startup, check files/input for any files, and run those first.  Those are files which were processing when the server died.
		Clients may be looking for them.
	Remove output after it's been retrieved, or add a deletion function that clients can call after retrieval
'''
import sys
import ConfigParser
from Queue import Queue

# custom modules
import config

class jobStatus:
	'''
	This is an enumeration for the status of jobs
	'''
	notFound, error, enqueued, dequeued, done = range(5)

if __name__ == "__main__":
	# config
	CFG = ConfigParser.ConfigParser()
	config.load(CFG)

	if CFG.has_section('all') and CFG.has_option('all', 'pythonpath'):
		pypath = CFG.get('all', 'pythonpath').split(':');
		sys.path.extend(pypath)

	# additional modules
	#from server.singleProcess import singleProcess
	#from server.requestHandler import requestHandler
	#from server.watchdog import watchdog
	from server.server import Server
	#from server import utils

	try:
		s = Server(CFG)
		s.run()
		#only the main thread can catch signals.
	finally:
		try:
			s.server.close()
		except Exception:
			pass
