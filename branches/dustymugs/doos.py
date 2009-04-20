#!/usr/bin/env python

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
