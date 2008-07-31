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
            self.jobQueue.put('terminate', True) #singleProcess threads will terminate when they process this as a job.  There's one for each thread.
        self.jobQueue.join()


class dataGrabber(threading.Thread):
    def __init__(self,client, server):
        threading.Thread.__init__(self)
        self.client = client
        self.size = server.size
        self.server = server
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
                if bytesExpected is None:
                    buf = "".join(data_chunks)
                    i = buf.find("|")
                    if i is not -1:
                        bytesExpected = int(buf[:i])
                        data_chunks = [ buf[i+1:] ]
                        bytesGotten = len( data_chunks[0] )
                    else:
                        bytesGotten += len(buf)

                if bytesExpected is None or bytesGotten < bytesExpected:
                    buf = self.client.recv(self.size)
                else:
                    break
            
            #data_chunks is a list of chunks of the data.  Join them together.
            data = "".join(data_chunks)
            data = data.split('|', 1) #pull out the checksum from the data
            checksum = data[0]
            data = data[1]
            
            #get the sha1 hash for checksumming
            m = hashlib.sha1()
            m.update(data)
            if (m.hexdigest() != checksum):
                raise Exception("Checksum failed! ")
            
            self.client.sendall( str(len(data)) )
            if data == 'terminate':
                self.server.terminate()
            else:#or else we're good to put it in the queue
                self.server.jobQueue.put( data, True )
            
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