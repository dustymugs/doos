#!/usr/bin/env python

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

import os,sys
import ConfigParser

# change working directory
os.chdir(os.path.dirname(sys.argv[0]))

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
