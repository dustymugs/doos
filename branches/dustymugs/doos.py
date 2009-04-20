#!/usr/bin/env python

"""
A process management server that uses threads to handle multiple jobs and clients at a time.
Entering any line of input at the terminal will exit the server.

When a client sends a job, he is assigned a ticket number which uniquely identifies the job in the system.
The input sent by the client is stored in [workspace]/files/input/**ticket number**
When the job processing is finished, the job is stored in [workspace]/files/output/**ticket number**

The protocol for all client REQUEST is:

	{NUMBER OF BYTES FOLLOWING THE PIPE}|{SHA1 CHECKSUM OF EVERYTHING FOLLOWING THE PIPE}|{ARGUMENTS}::file start::[{FILE0 NAME}::file content::{FILE0 CONTENT}::file end::[::file start::{FILEX NAME}::file content::{FILEX CONTENT}::file end::]]

	'::file start::', '::file content::' and '::file end::' are tokens

	FILE0 is always the script to run while FILEX is for other files needed by the script

	The ARGUMENTS string coming from the client should be formatted as follows:
		key1=value1;key2=value2;key3;key4;key5=value5  (etc)

	Valid KEYS are:
		terminate
			- instruct the server to shutdown
			- value is OPTIONAL
		prepareJob
			- add new job to server
			- return should be job ticket
			- the key "initFunc" is a dependent argument
				- ex: prepareJob;initFunc=Main
			- value is OPTIONAL
		initFunc
			- value is the name of function to be launched
			- depends upon the key preparejob
			- value is REQUIRED
		returnJob
			- get the output of job using provided ticket
			- response will be the job output
			- the key "ticket" is required
				- ex: returnJob;ticket=123456
			- value is OPTIONAL
		statusJob
			- get the status of job using provided ticket
			- response will be job's status file
			- the key "ticket" is required
				- ex: statusJob;ticket=123456
			- value is OPTIONAL
		deleteJob
			- delete the output files of a job using provided ticket
			- TODO: have command remove job from queue if job not processed yet
			- the key "ticket" is required
				- ex: deleteJob;ticket=123456
			- value is OPTIONAL
		ticket
			- value is REQUIRED

When a client requests a ticket, the system searches the output folder for the ticket as a filename and returns the file if found.
	If that file is not found, but it is found in input/, then the server responds that the job is still being processed
	if that file is not found in either folder, the server replies that the ticket id is unknown

The protocol for any server RESPONSE is:
	{NUMBER OF BYTES FOLLOWING THE PIPE}|{SHA1 CHECKSUM OF EVERYTHING FOLLOWING THE PIPE}|[{SERVER RESPONSE}][::file start::{FILE0 NAME}::file content::{FILE0 CONTENT}::file end::[::file start::{FILEX NAME}::file content::{FILEX CONTENT}::file end::]]

"""

'''
TODO:
	Fix exception handling with socket events
	If you restart a server, you'll get "Could not start up, socket in use."  Figure out how to make it work, or just quit.
	On server startup, check files/input for any files, and run those first.  Those are files which were processing when the server died.
		Clients may be looking for them.
'''

import sys
import ConfigParser

# custom modules
import config

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
	# Ctrl+C input
	except KeyboardInterrupt:
		s.log("Server instructed to shutdown by keyboard.")
		s.terminate()
	finally:
		try:
			s.server.close()
		except Exception:
			pass
