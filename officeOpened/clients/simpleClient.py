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
    # read from keyboard
    line = sys.stdin.readline()
    line = 'initial function!|' + line[:-1] #strip out that last \n
    if line == '':
        break
    
    #get the sha1 hash for checksumming
    m = hashlib.sha1()
    m.update(line)
    checksum = m.hexdigest()

    s.sendall( str(len(line)) + '|' + checksum + '|' + line)
    sys.stdout.write("sending:\n" + str(len(line)) + '|' + checksum + '|' + line + "\n")
    data = s.recv(size)
    sys.stdout.write(data)
    sys.stdout.write('%')
    s.close()
s.close()