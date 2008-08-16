#!/usr/bin/env python

"""
An echo server that uses threads to handle multiple clients at a time.
Entering any line of input at the terminal will exit the server.

When a client sends a job, he is assigned a ticket number which uniquely identifies the job in the system.
The input sent by the client is stored in homeDirectories/input/**ticket number**
When the job processing is finished, the job is stored in homeDirectories/output/**ticket number**

The protocol for any client request is this:

number of bytes following the pipe|checksum of everything following the pipe|arguments::file start::fileContents
( "::file start::" is a token )
The arguments string coming from the client should be formatted as follows:
    key1=value1;key2=value2;key3;key4;key5=value5  (etc)

When a client requests a ticket, the system searches the output folder for the ticket as a filename and returns the file if found.
    If that file is not found, but it is found in input/, then the server responds that the job is still being processed
    if that file is not found in either folder, the server replies that the ticket id is unknown
"""
'''
TODO: 
    Fix exception handling with socket events
    If you restart a server, you'll get "Could not start up, socket in use" which skips killing everyone and quits.  Kill everyone first.
    On server startup, check files/input for any files, and run those first.  Those are files which were processing when the server died.
        Clients may be looking for them.
    Kill everyone who ignores SIGTERM
    Remove output after it's been retrieved, or add a deletion function that clients can call after retrieval
    Make sure that <<defunct>> processes don't display weirdly with this usage of ps
    os.waitpid() isn't catching murdered processes.  Find out why.
    
    ZOMBIES:
        wait() for murthered processes to finish.
        Create a signal handler for children that die and reap their souls
        Does killing still send SIGCHLD?
    
'''
import select
import socket
import sys
import os
import threading
from Queue import Queue
import hashlib
from server.singleProcess import singleProcess
from server import officeOpenedUtils
import random
import datetime
import time

class Server:
    def __init__(self, numSingleProcesses=4):
        self.host = '' #socket.getsockname()
        self.port = 8568
        self.backlog = 100 #the maximum number of waiting socket connections
        self.size = 4096
        self.server = None
        self.jobQueue = Queue()
        self.outputQueue = Queue()
        self.singleProcesses = {}
        self.running = True
        self.input = []
        self.watchdog = watchdog(self, interval=5, timeout=60)
        self.waitMutex = threading.Lock()
        self.serverSocketTimeout = 30
        
        #Create numsingleProcesses singleProcess's, indexed by an id.
        for i in range(numSingleProcesses):
            i = str(i)
            self.singleProcesses[i] = singleProcess( i, self.jobQueue, self.watchdog, self.waitMutex )
            self.singleProcesses[i].start()
            self.watchdog.addThread( i, self.singleProcesses[i].getPIDs() )
            
        self.watchdog.start()
            
    def terminate(self):
        self.running = False

    def run(self):
        while True:
            try:
                self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server.bind((self.host,self.port))
                self.server.listen(self.backlog)
                break
            except socket.error, (value, message):
                if self.serverSocketTimeout > 0:
                    print "Socket error. Retrying in 2 seconds...\n"
                    time.sleep(2)
                    self.serverSocketTimeout -= 2
                else:
                    print "Could not open server listening socket: Connection attempts timed out.\n"
                    self.server = None
                    break
            except Exception, (message):
                print "Could not open server listening socket: " + str(message) + "\n"
                break
        
        if self.server is not None:        
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
                            print 'Error connecting to client:\n' + str(value) + "\n" + str(message)
                    
                    #a connected client has sent data for us to process
                    elif type(s) == type(self.server): #if it's not the server socket, but it is a socket,
                        grabber = requestHandler (s, self)  #create a thread to handle the request
                        self.input.remove ( s ) #tell the server thread to stop looking for input on this socket
                        grabber.start()
    
                    elif s == sys.stdin:
                        # handle standard input
                        junk = sys.stdin.readline()
                        self.running = 0
                        
            self.server.close()
        #exiting gracefully; allow all threads to finish before closing
        # close all threads
        for c in self.singleProcesses:
            self.jobQueue.put( 'terminate', True) #singleProcess threads will terminate when they process this as a job.  There's one for each thread.
        self.jobQueue.join()
        #the watchdog will shut itself down when all threads have removed themselves from its list.

'''class blackStork(threading.Thread):
    ''
    This thread waits for our children to die and takes them back to the Source (reaps them).
    ''
    def __init__(self, watchdog):
        threading.Thread.__init__(self, name="blackStork")
        self.watchdog = watchdog
        
    def run(self):
        #Handle dying children.
        #this loop's condition will be tested on init or when all of the children have died, be it because the server's shutting down
        #or because all child processes have crashed and none have yet been restarted
        while self.watchdog.readyToExit is False:
            #os.waitpid will throw an OSError exception when this process has no children
            try:
                while True:
                    pid, exit = os.waitpid(0, os.WUNTRACED) #await the death of any process in this process group
                    self.watchdog.dropProcesses([str(pid)], True) #notify the watchdog that the process has died, which will then tell the thread
                    print "Child " + str(pid) + " has died.  So it goes.\n"
            except OSError, (value, message):
                if value is 10: #error 10 means that there are no children to wait for
                    #this can happen if all child processes have crashed, in which case we don't want to exit
                    #so we must also make sure that watchdog says we're ready to exit before closing down the thread
                    if self.watchdog.readyToExit:
                        self.clear()
                        break
                else:
                    raise OSError(value, message)
          
    def clear(self):
        self.watchdog = None
'''

class watchdog(threading.Thread):
    '''
    This thread checks every *interval* seconds (usually 5 seconds) to make sure of the following:
    
        Are the threads which have jobs are still using CPU time? Or if they are, has the job been running for less time than the timeout?
        If not:
            kill the thread (if it even exists)
            log the error in output/ticket/status.txt
            if the job has died before:
                Restart the thread with job it died on.
            else:
                log a fatal error in status.txt
        Are the processes still alive?
            If not, start them up again
            
    self.threads is of the form:
     [
         "0": [parent, child, child], 
         "1": [parent], 
         "2": [parent, child] ]       
    ]    (etc.)  where parent and child are string representations of process IDs
    
    TODO: handle dying children
    '''
    def __init__(self, server, interval=5, timeout=30):
        threading.Thread.__init__(self, name="watchdog")
        self.interval = interval
        self.timeout = timeout
        self.threads = {} #the threads being watched over.  Not linking to server.threads because we don't want circular references
        self.threadsMutex = threading.Lock()
        self.running = True
        self.readyToExit = False #this is for the main thread's wait() loop. When all children have been reaped, this will be True
        self.server = server
        #self.blackStork = blackStork(self) #the watchdog owns and controls the black stork
        
    def run(self):
        #self.blackStork.start()
        
        while not self.readyToExit:
            time.sleep(self.interval)
            
            #need to acquire a lock here for the threads list since hatching and dying threads can modify this list
            self.threadsMutex.acquire()
            
            if self.threads is {}: #then all threads have been removed and it's time to shut down
                self.clear()
            else:
                processes = officeOpenedUtils.checkProcesses( self.threads, self.server.waitMutex )
                print "----------------\n" + "Watchdog sees the following process usage:\n" + str(processes) + "\n----------------\n"
            self.threadsMutex.release()
            
    def clear(self):
        self.readyToExit = True
        self.server = None
        #self.blackStork.join(30)
        
    def checkForDeadChildren(self):
        '''
        This function calls a non-blocking wait on the direct children of the server.
        Any call to subprocess or Popen which depends on the returned value of the process it starts
            must LOCK the server.waitMutex before starting the process.  This is because
            the exit status of a process can only be retrieved once, and without setting that mutex,
            this function may absorb the necessary information.
        '''
        #Handle dying children.
        #this loop's condition will be tested on init or when all of the children have died, be it because the server's shutting down
        #or because all child processes have crashed and none have yet been restarted
        deadChildren = []
        while True:
            self.server.waitMutex.acquire()
            pid, exit = os.waitpid(-1, os.WUNTRACED | os.WNOHANG) #look for the death of a direct child of this process
            self.server.waitMutex.release()
            if pid == 0:
                break
            deadChildren.append( str(pid) )
            print "Child " + str(pid) + " has died.  So it goes.\n"
        
        if len(deadChildren) > 0:
            self.dropProcesses(deadChildren, True) #notify the watchdog that the process has died, which will then tell the thread
        
    
    def removeThread(self, threadId):
        '''
        Remove the specified thread from the list over which watchdog watches
        '''
        self.threadsMutex.acquire()
        
        try:
            del self.threads[threadId]
        except KeyError: #if that threadId doesn't exist in the dictionary
            print "watchdog failed to remove threadId '" + threadId + "' because it is not in its list.\n"
        except Exception, (message):
            print "watchdog failed to remove threadId '" + threadId + "': " + str(message)
            
        self.threadsMutex.release()
        
    def addThread(self, threadId, processes):
        '''
        add the thread to watchdog's list.
        Optionally include processes to watch over
        '''
        if processes == None:
            processes = []
            
        self.updateProcesses(threadId, processes)
        
    def updateProcesses(self, threadId, processes):
        '''
        Update the list of associated processes for the given threadId
            to the new list (processes)
        '''
        self.threadsMutex.acquire()
        self.threads[threadId] = processes
        self.threadsMutex.release()
        
    def dropProcesses(self, processes, notifyThread=True):
        '''
        Stop watching these processes.  processes can be a string if it's a single process, or a list of strings.
        If notifyThread is True, the threads associated with each of the dropped processes will be notified that 
        they've been dropped (if the thread didn't call this itself, the process probably died and was taken by 
        the blackStork).
        '''
        #if it's a single string, make it a list
        if type(processes) == type( '' ):
            processes = [processes]
        
        #the list of dropped processes will be sent to the appropriate thread
        #dropped will store the dropped processes, grouped by threadId
        dropped = {}
            
        self.threadsMutex.acquire()
        
        #search through all of the processes in each thread to see if this process was being watched
        for threadId, thread in self.threads:
            for watched in thread:
                if watched in processes:
                    self.threads[threadId].remove(watched)
                    processes.remove(watched)
                    
                    if notifyThread:
                        if not threadId in dropped:
                            dropped[threadId] = []
                        dropped[threadId].append(watched)
              
        self.threadsMutex.release()
        
        #if notifyThread is False, dropped will be empty
        for threadId in dropped:
            self.server.singleProcesses[threadId].deathNotify(dropped[threadId])
        
    
            
            


#this is an enumeration for the status of jobs
class jobStatus:
    notFound, error, enqueued, dequeued, done = range(5)
    
class requestHandler(threading.Thread):
    def __init__(self,client, server):
        threading.Thread.__init__(self, name="requestHandler")
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
                    i = buf.find("|")  #fields are delimited by | like so: bytesExpected|checkSum|argString|data
                                        #args is structred thus: "key1=value1;key2=value2;key3;key4;key5=value5"  etc
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
                try:
                    self.client.sendall( "Checksum failed!" )
                finally:
                    raise Exception("Checksum failed! ")
            
            argString, data = data.split('::file start::', 1)
            
            #convert argString into a key-value dictionary
            args = officeOpenedUtils.makeDictionary(argString)
            
            if args.has_key('terminate') and args['terminate']: #guard against "terminate=false"
                try:
                    self.client.sendall( "shutting down...\n" )
                finally:
                    self.server.terminate() #tell the server to shut down all threads
            
            #if they want to put it in the queue, dump the data to a file and enqueue
            elif args.has_key('prepareJob') and args['prepareJob'] is True:   
                self.prepareJob(argString, data)
            
            #if they want status or they want the job    
            elif ( (args.has_key('stat') and args['stat']) or (args.has_key('returnJob') and args['returnJob']) ) and args.has_key('ticket'):
                logfile, status = self.stat(args['ticket']) #get the file containing the job's status
                
                if status == jobStatus.notFound:
                    self.client.sendall( "STATUS " + str(status) + ": " + str(logfile) )
                elif (args.has_key('returnJob') and args['returnJob']) and status == jobStatus.done:
                    self.returnJob( args['ticket'] )
                else:
                    self.client.sendall(logfile)
            else:
                self.client.sendall("STATUS " + jobStatus.error + ": Unknown command\n")
                
                
        except socket.error, (message):
            print "Socket error:\n" + str(message) + "\n"
        except Exception, (message):
            print str(message)
        finally:
            #now close the connection 
            self.client.close()
    
    def returnJob(self, ticket):
        '''
        Send the completed job back to the client.  First look for files.zip, and if that
        doesn't exist look for the folder "files" and send its contents.
        data is stored as follows: [ (filename, data) ]
        '''
        isZip = None #start off assuming that zipping the output didn't work
        try:
            file = open(self.home + "files/output/" + ticket + "/files.zip")
            data = [ ('files.zip', file.read()) ]
            file.close()
            isZip = True
        except IOError, (value, message): 
            #if the file is not found, the ticket doesn't exist.
            #zipping the output probably failed, meaning we probably have a HUGE file/set of files
            #Either that, or there was some unknown IO error.
            #Now we're going to try to read all of the files and load them
            #into data.
            try:
                data = []
                absoluteRoot = self.home + 'files/output/' + ticket + '/files/'
                for root, dirs, files in os.walk(self.home + 'files/output/' + ticket + '/files/'):
                    for filename in files:
                        #find relative root for the file's path
                        (junk, relativeRoot) = root.split(absoluteRoot, 1)
                        file = open(relativeRoot + filename)
                        data.append( (relativeRoot + filename, file.read()) )
                        file.close()
                isZip = False #mark that the output is a number of files, not just a single zip file
                
            #if we couldn't read all of the files
            except Exception, (message):
                try:
                    self.client.sendall('STATUS ' + str(jobStatus.error) + ": " + str(message))
                except Exception, (message):
                    print "Unknown Error: " + str(message)
        
        except socket.error, (message):
            print "Socket Error: " + str(message)
        except Exception, (message):
            print "Unknown Error: " + str(message)
        
        #So now we have the data (or failure).  Let's send the data back to the client.
        try:
            if isZip is not None:
                for file in data:
                    self.client.sendall( file[0] + "::file start::" + file[1] + "::fileEnd")
        except socket.error, (message):
            print "Socket Error: " + str(message)
        except Exception, (message):
            print "Unknown Error: " + str(message)
    
    def stat(self, ticket):
        try:
            file = open(self.home + "files/output/" + ticket + "/status.txt")
            logfile = file.read()
            file.close()
        except IOError, (value, message): #if the file is not found, the ticket doesn't exist.
            if value == 2:
                return "Ticket not found.\n", jobStatus.notFound
            else:
                return str(message), jobStatus.error
        except Exception, (message):
            return "Unknown Error: " + str(message), jobStatus.error
            
        if logfile.find('timeCompleted:') >= 0:
            return logfile, jobStatus.done
        elif logfile.find('timeDequeued:') >= 0:
            return logfile, jobStatus.dequeued
        else:
            return logfile, jobStatus.enqueued
        
            
    def prepareJob(self, argString, data):
        #if the file already exists, keep generating a random filename until an available one is found
        #keep checking the output folder too because this filename will be the unique ticket number, and
        #if there's a file there, that ticket is in the system (and waiting for some client to come claim it)
        randgen = random.Random()
        randgen.seed()
        filename = str( randgen.randint(0,15999999) )
        
        while os.path.exists(self.home + 'files/input/' + filename + '.data') \
                or os.path.exists(self.home + 'files/output/' + filename):
            filename = str( randgen.randint(0,15999999) )
        #path to the input file
        dirpath = self.home + 'files/input/' + filename
        file = open(dirpath + '.data', 'w')
        file.write( data ) #save the data
        file.close()
        
        #now write arguments to the handler for this command to a file
        file = open(dirpath + '.args', 'w')
        file.write(argString)
        file.close()
        #now create a directory for the job status file status.txt to be stored
        os.mkdir(self.home + 'files/output/' + filename)
        file = open(self.home + 'files/output/' + filename + '/status.txt', 'w')
        #log the date and time
        file.write('timeEntered:' + datetime.datetime.utcnow().isoformat())
        file.close()
        #finally, put the data into the queue
        self.server.jobQueue.put( dirpath, True )
        self.client.sendall( "transmission ok\nticket number:" + filename + "\n")
        
if __name__ == "__main__":
    s = Server()
    s.run()
    #only the main thread can catch signals.  
    