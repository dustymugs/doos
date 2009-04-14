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
    args = 'prepareJob;initFunc=Main'
    # read from keyboard
    line = sys.stdin.readline()
    if line[:5] == 'file ':
        file = open('/home/clint/OOo/' + line[5:-1] + '.script')
        line = args + '::file start::' + file.read()
        file.close()
    elif line == 'busy\n':
        file = open('/home/clint/OOo/busy.script')
        line = args + '::file start::' + file.read()
        file.close()
    elif line == 'sample\n':
        file = open('/home/clint/OOo/sample.script')
        line = args + '::file start::' + file.read()
        file.close()
    elif line == '\n':
        break
    else: #for sending raw commands
        line = line[:-1] + '::file start::'
    #else:
    #    line = args + '::file start::' + line[:-1] #strip out that last \n
        
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host,port))
    
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