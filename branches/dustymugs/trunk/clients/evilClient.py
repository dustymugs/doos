#!/usr/bin/env python

"""
Bombards the server with traffic
"""

import socket
import sys
import random

host = '192.168.137.104'
port = 8568
#size = 65536
randgen = random.Random()
randgen.seed()

for i in xrange(0,200):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host,port))
    line = (str(i) * randgen.randint(10000000, 20000000))
    lenSent = len(line)
    print 'Iteration ' + `i` + ': Sending ' + `lenSent` + 'chars...'
    s.sendall(line)
    s.sendall('***endTransmission***')
    print 'done. Waiting for response...'
    data = s.recv( 4096 )
    print 'done (' + str( data ) + ' chars)\n'
    if not lenSent==long(data):
        print "\nMISMATCHING ERROR!!!\n"
    s.close() 
