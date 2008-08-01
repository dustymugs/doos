#!/usr/bin/env python

"""
An echo server that uses threads to handle multiple clients at a time.
Entering any line of input at the terminal will exit the server.
"""
'''
TODO: fix exception handling with socket events
'''
import select
import socket
import sys
from os import path
import threading
from Queue import Queue
import hashlib
from server.singleProcess import singleProcess

class Server:
    def __init__(self):
        self.host = '' #socket.getsockname()
        self.port = 8568
        self.backlog = 100 #the maximum number of waiting socket connections
        self.size = 4096
        self.server = None
        self.jobQueue = Queue()
        self.outputQueue = Queue()
        self.dataThreads = []
        self.singleProcesses = []
        self.running = True
        self.input = []
        
        #Create numsingleProcesses singleProcess's, indexed by an id.
        numsingleProcesses = 4
        for i in range(numsingleProcesses):
            self.singleProcesses.append( singleProcess(i, self.jobQueue, self) )
            self.singleProcesses[i].start()


    def open_socket(self):
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.bind((self.host,self.port))
            self.server.listen(self.backlog)
        except socket.error, (value,message):
            if self.server:
                self.server.close()
            print "Could not open socket: " + message
            sys.exit(1)
            
    def terminate(self):
        self.running = False

    def run(self):
        self.open_socket()
        #start the singleProcess threads
        self.input = [self.server,sys.stdin]
        running = 1
        while self.running:
            #choose among the input sources which are ready to give data.  Choosing between stdin, the server socket, and established client connections
            inputready,outputready,exceptready = select.select(self.input,[],[])
            
            for s in inputready:
                #print 'Got input: ' + str(s) + '\n'
                if not running:
                    break
                    
                elif s == self.server:
                    # handle the server socket (for when someone is trying to connect)
                    try:
                        client, address = self.server.accept()
                        self.input.append(client)
                        client.setblocking(0)
                    except socket.error, (value, message):
                        #do nothing--we've probably just connected without the client having sent any data
                        print 'Error connecting to client:\n' + str(value) + "\n" + message
                
                #a connected client has sent data for us to process
                elif type(s) == type(self.server): #if it's not the server socket, but it is a socket,
                    grabber = dataGrabber (s, self)  #create a thread to receive the data
                    self.input.remove ( s ) #tell the server thread to stop looking for input on this socket
                    grabber.start()
                    self.dataThreads.append( grabber )

                elif s == sys.stdin:
                    # handle standard input
                    junk = sys.stdin.readline()
                    self.running = 0

        #exiting gracefully; allow all threads to finish before closing
        # close all threads
        self.server.close()
        for c in self.singleProcesses:
            self.jobQueue.put( (None, 'terminate'), True) #singleProcess threads will terminate when they process this as a job.  There's one for each thread.
        self.jobQueue.join()


class dataGrabber(threading.Thread):
    def __init__(self,client, server):
        threading.Thread.__init__(self)
        self.client = client
        self.size = server.size
        self.server = server
        self.home = "/home/clint/officeOpened/homeDirectories/"
        client.setblocking(1)
        client.settimeout(60.0)

    def run(self):
        try:
            data_chunks = [] #we're just concatenating the chunks of data received, but this is faster than string concatenation
            buf = self.client.recv(self.size)
            bytesExpected = None
            bytesGotten = 0
            
            while True: #the first part of the message, up to '|', is the length of the transmission.  Keep going till it's been exceeded
                if buf == '':
                    raise socket.error("Socket has been broken before transmission completed. It probably failed.")
                data_chunks.append(buf)
                #find out how many bytes will be sent
                if bytesExpected is None:  #if we still haven't determined the number of bytes to expect
                    buf = "".join(data_chunks) #in case the bytesExpected number was in another buffering, join whatever we've got
                    i = buf.find("|")  #fields are delimited by | like so: bytesExpected|checkSum|args|data
                    if i is not -1:  #if | is found, then we have the bytesExpected
                        bytesExpected = int(buf[:i])  #bytesExpected is the string from the beginning until the |
                        data_chunks = [ buf[i+1:] ]  #we probably have more than just bytesExpected in the buffer, so store that data
                        bytesGotten = len( data_chunks[0] )

                #if we're still determining the number of bytes to expect or we're still downloading the file,
                if bytesExpected is None or bytesGotten < bytesExpected:
                    buf = self.client.recv(self.size)  #get more data
                else:
                    break  #otherwise we're done.
            
            #data_chunks is a list of chunks of the data.  Join them together.
            data = "".join(data_chunks)
            checksum, data = data.split('|', 1) #pull out the checksum from the data
            
            #get the sha1 hash for checksumming
            m = hashlib.sha1()
            m.update(data)
            if (m.hexdigest() != checksum):
                raise Exception("Checksum failed! ")
            
            #DEBUG: send back the checksum
            self.client.sendall( str( m.hexdigest() ) )
            if data == 'terminate':
                self.server.terminate() #tell the server to shut down all threads
            else:   #or else we're good to put it in the queue
                    #so dump the data to a file
                
                args, data = data.split('::file start::', 1)
                dirpath = self.home + 'files/' + str(checksum)  #whose filename is the data's checksum
                
                while path.exists(dirpath):  #if the file already exists, keep generating a random filename until an available one is found
                    import random
                    randgen = random.Random()
                    randgen.seed()
                    dirpath = self.home + 'files/' + str( randgen.randint(0,15999999) )
                file = open(dirpath, 'w')
                file.write( data ) #save the data
                #finally, put the data into the queue
                self.server.jobQueue.put( (dirpath, args), True ) 
            
        except socket.error, (value, message):
            print "Error receiving data:\n" + str(value) + ': ' + message + "\n" + repr(self.client)
        except Exception, (message):
            print message
        finally:
            #now close the connection 
            self.client.close()


if __name__ == "__main__":
    s = Server()
    s.run() 