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
