#!/usr/bin/env python

"""
An echo client that allows the user to send multiple lines to the server.
Entering a blank line will exit the client.
"""

import socket
import sys
import hashlib

#host = '127.0.0.1'
host = '172.16.2.21'
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

		if line[:5] == 'file ':
			file = open('/home/dustymugs/Work/OOo/' + line[5:])
			line = args + '::file start::' + '::file content::' + file.read() + '::file end::'
			file.close()
		elif line[:5] == 'host ':
			print "Changing %s to %s" % (host, line[5:])
			host = line[5:]
			continue
		elif line == "busy":
			file = open('/home/dustymugs/Work/OOo/testwait.script')
			line = args + '::file start::' + '::file content::' + file.read() + '::file end::'
			file.close()
		elif line == "sample":
			file = open('/home/dustymugs/Work/OOo/test2.script')
			line = args + '::file start::' + '::file content::' + file.read() + '::file end::'
			file.close()
		elif line == "exit" or line == "":
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
