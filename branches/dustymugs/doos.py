#!/usr/bin/env python

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
