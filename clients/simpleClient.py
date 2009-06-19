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

"""
An echo client that allows the user to send multiple lines to the server.
Entering a blank line will exit the client.
"""

import socket
import sys
import hashlib

host = '127.0.0.1'
port = 8568
size = 4096

try:
	isArgv = False
	args = 'prepareJob;initFunc=Main'

	while 1:

		if (len(sys.argv) > 1) and not isArgv:
			isArgv = True

			i = 1
			line = []
			while i < len(sys.argv):
				line.append(sys.argv[i])
				i += 1
			line = ' '.join(line)
		else:
			sys.stdout.write('%')
			# read from keyboard
			line = sys.stdin.readline().rstrip()

		if line[:7] == 'script ':
			file = open(line[7:])
			line = args + '::file start::' + '::file content::' + file.read() + '::file end::'
			file.close()
		elif line[:5] == 'host ':
			print "Changing %s to %s" % (host, line[5:])
			host = line[5:]
			continue
		elif line == 'exit' or line == '':
			break
		else: #for sending raw commands
			line = line + '::file start::'

		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect((host,port))

			#get the sha1 hash for checksumming
			m = hashlib.sha1()
			m.update(line)
			checksum = str( m.hexdigest() )
			line = checksum + '|' + line

			sys.stdout.write("SEND:\n" + str(len(line)) + '|' + line + "\n")
			s.sendall( str(len(line)) + '|' + line)

			data = s.recv(size)
			sys.stdout.write("RECEIVE:\n" + data + "\n")

			s.close()
		except Exception:
			pass
		finally:
			pass

		if isArgv:
			break

# Ctrl+C input
except KeyboardInterrupt:
	print
	sys.exit(0)
finally:
	try:
		s.close()
	except Exception:
		pass
