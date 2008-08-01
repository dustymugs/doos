#!/usr/bin/env python

"""
An echo client that allows the user to send multiple lines to the server.
Entering a blank line will exit the client.
"""

import socket
import sys
import hashlib

host = '192.168.137.104'
port = 8568
size = 4096
sys.stdout.write('%')

while 1:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host,port))
    args = 'Main'
    # read from keyboard
    line = sys.stdin.readline()
    if line == 'sample.script\n':
        file = open('/home/clint/OOo/sample.script')
        line = args + '::file start::' + file.read()
        file.close()
    elif line == '':
        break
    else:
        line = args + '::file start::' + line[:-1] #strip out that last \n
    
    
    #get the sha1 hash for checksumming
    m = hashlib.sha1()
    m.update(line)
    checksum = str( m.hexdigest() )
    line = checksum + '|' + line

    s.sendall( str(len(line)) + '|' + line)
    sys.stdout.write("sending:\n" + str(len(line)) + '|' + line + "\n")
    data = s.recv(size)
    sys.stdout.write(data + "\n(was received)\n\n")
    sys.stdout.write('%')
    s.close()
s.close()