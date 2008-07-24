#!/usr/bin/env python

"""
An echo client that allows the user to send multiple lines to the server.
Entering a blank line will exit the client.
"""

import socket
import sys

host = '192.168.137.104'
port = 8568
size = 4096
sys.stdout.write('%')

while 1:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host,port))
    # read from keyboard
    line = sys.stdin.readline()
    if line == ' ':
        break
    s.sendall(line[:-1] + '***endTransmission***') #strip out that last \n
    data = s.recv(size)
    sys.stdout.write(data)
    sys.stdout.write('%')
    s.close()
s.close()