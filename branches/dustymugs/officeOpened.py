#!/usr/bin/env python

"""
A process management server that uses threads to handle multiple jobs and clients at a time.
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
    If you restart a server, you'll get "Could not start up, socket in use."  Figure out how to make it work, or just quit.
    On server startup, check files/input for any files, and run those first.  Those are files which were processing when the server died.
        Clients may be looking for them.
    Remove output after it's been retrieved, or add a deletion function that clients can call after retrieval
'''
import select
import socket
import sys
import os
import threading
from Queue import Queue
import hashlib
from server.singleProcess import singleProcess
from server import utils.py
import random
import datetime
import time

class Server:
    def __init__(self, numSingleProcesses=4):
        self.host = '' #socket.getsockname()
        self.port = 8568
        self.backlog = 100 #the maximum number of waiting socket connections
        self.socketBufferSize = 4096
        self.logfile = open('/home/dustymugs/Work/OOo/doos-dustymugs/home/logs/server.log', 'a')
        self.logMutex = threading.Lock()
        self.server = None
        self.jobQueue = Queue()

        #this keeps track of which thread has which job
        self.singleProcesses = {}

        self.running = True
        self.input = []
        self.watchdog = watchdog(self, interval=2, jobTimeout=10)
        self.waitMutex = threading.Lock()
        self.serverSocketTimeout = 30
        
        self.log("Starting " + str(numSingleProcesses) + " singleProcess instances.")
        
        #Create numsingleProcesses singleProcess's, indexed by an id.
        for i in range(numSingleProcesses):
            i = str(i)
            self.log("Starting thread 'singleProcess" + i + "'.")
            self.watchdog.addThread(i)
            self.singleProcesses[i] = singleProcess( i, self )
            self.singleProcesses[i].start()
        
        self.log("Starting thread 'watchdog'.")
        self.watchdog.start()
    
    def log(self, message, level="information"):
        # Log message to the server's logfile, preceeded by a timestamp and a severity level
        timeLogged = datetime.datetime.now().isoformat()
        self.logMutex.acquire()
        self.logfile.write( timeLogged + '\t' + str(level) + '\t' + str(message) + "\n")
        self.logfile.flush() #be sure to flush the message out to the logfile
        self.logMutex.release()
        
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
                    self.log("Socket error. Retrying in 2 seconds...", "error\t")
                    time.sleep(2)
                    self.serverSocketTimeout -= 2
                else:
                    self.log("Could not open server listening socket: Connection attempts timed out.", "abort")
                    self.server = None
                    break
            except Exception, (message):
                self.log("Could not open server listening socket: " + str(message), "abort")
                break
        
        if self.server is not None:        
            self.log("Server listening on port " + str(self.port))
            #start the singleProcess threads
            self.input = [self.server]
            running = 1
            while self.running:
                #choose among the input sources which are ready to give data.  Choosing between stdin, the server socket, and established client connections
                inputready,outputready,exceptready = select.select(self.input,[],[])
                
                for s in inputready:
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
                            self.log('Error connecting to client:\n' + str(value) + "\n" + str(message), 'error\t')
                    
                    #a connected client has sent data for us to process
                    elif type(s) == type(self.server): #if it's not the server socket, but it is a socket,
                        grabber = requestHandler (s, self)  #create a thread to handle the request
                        self.input.remove ( s ) #tell the server thread to stop looking for input on this socket
                        grabber.start()
                        
            self.server.close()
        #exiting gracefully; allow all threads to finish before closing
        # close all threads
        self.log("Queueing 'terminate' for each singleProcess instance.")
        for c in self.singleProcesses:
            self.jobQueue.put( 'terminate', True) #singleProcess threads will terminate when they process this as a job.  There's one for each thread.
        self.jobQueue.join()
        #the watchdog will shut itself down when all threads have removed themselves from its list.
        
        
    def __del__(self):
        self.logfile.close()

class watchdog(threading.Thread):
    '''
    This thread checks every *interval* seconds (usually 5 seconds) to make sure of the following:
    
        For the threads which have jobs:
            If they're still running after self.timeout and they haven't been using much CPU time, kill them.
                else if they're still running but are using a fair amount of CPU time, give them 1/2 of self.timeout longer to run.
        
        Have any processes died since the last time watchdog was awake?
            If so, inform the appropriate threads (which will then restart them)
    
    self.threads keeps track of what each thread is and is supposed to be up to.  Each threadId has a key.  Each element of 
    self.threads represents one thread, and is itself a dictionary with the following keys:
    
        "ticket": a string representing the ticket number of the job being worked on, or "ready" if the thread is idle
        "processes": a list of the strings, each representing a Process ID which was spawned by the thread
        "extensions granted": the number of times that the job has been given extra time over the default timeout
        "timestamp": the time the most recent job was accepted by the thread (approximately timeDequeued in status.txt)
        "cpu": the sum of the cpu usage samples taken for the current job
    
    
    self.threads is of the form:
     [
         "0": { "ticket":'2423528', "processes":["123", "124", "125"], "extensions granted":0, "timestamp":1219194339.800941, "cpu": 10.3 }, 
         "1": { "ticket":'171471', "processes":["588"], "extensions granted":1, "timestamp":1219194335.857452, "cpu": 15.3 }, 
         "2": { "ticket":'ready', "processes":["242", "243", "245"], "extensions granted":0, "timestamp":1219194339.800941, "cpu": 0.4 }
    ]    (etc.)  
                    where the index is the thread id, and parent and child are string representations of process IDs
                    The PID of the parent process always goes first in the "processes" list.
                    The purpose of differentiating the parent is so that utils.kill() can send SIGTERM
                    to the parent and giving it an opportunity to bury its children.  Failing that, it'll send 
                    SIGKILL to whoever is still alive among the parent and its children.
    '''
    def __init__(self, server, interval=5, jobTimeout=30):
        threading.Thread.__init__(self, name="watchdog")
        self.interval = datetime.timedelta(seconds=interval) #the number of seconds for which watchdog sleeps after checking the threads
        self.jobTimeout = datetime.timedelta(seconds=jobTimeout) #the normal length of time a job has to complete before being killed
        self.maxExtensions = 1 #maximum number of time extensions over the jobTimeout that can be given if the thread is still using the CPU
        self.minCPU = 10.0 #the minimum average of the percent of the CPU which a thread must be using to be kept alive past the jobTimeout
        self.threads = {} #information about the threads being watched over
        self.threadsMutex = threading.Lock()
        self.running = True
        self.readyToExit = False #this is for the main thread's wait() loop. When all children have been reaped, this will be True
        self.server = server
        self.log = server.log
        
    def run(self):
        # The main execution function for watchdog
        while not self.readyToExit:
            time.sleep(self.interval.seconds)
            
            #check to see if any children have died, and reap them if they have.  Then notify the parents.
            self.blackStork()
            #need to acquire a lock here for the threads list since hatching and dying threads can modify this list
            self.threadsMutex.acquire()
            
            if self.threads == {}: #then all threads have been removed and it's time to shut down
                self.clear()
            else:
                processes = utils.checkProcesses( self.threads, self.server.waitMutex )
                
                try:
                    for threadId in self.threads.keys():
                        #if this thread is processing a job, determine whether or not it's been running too long
                        if not self.threads[threadId]['ticket'] is 'ready':
                            #first add this interval's sample of the CPU usage
                            self.threads[threadId]["cpu"] += processes[threadId][0]
                            #if the job has been running longer than self.jobTimeout seconds
                            if self.jobTimeout < ( datetime.datetime.now() - self.threads[threadId]["timestamp"] ):
                                #if there haven't been too many extensions granted, and the average CPU usage has been at least self.minCPU
                                if self.threads[threadId]["extensions granted"] < self.maxExtensions and \
                                        self.threads[threadId]["cpu"] / ( self.jobTimeout.seconds // self.interval.seconds ) > self.minCPU:
                                    self.threads[threadId]["extensions granted"] += 1 #note that another extension has been granted
                                    self.threads[threadId]["timestamp"] += self.jobTimeout / 2 #pretends that the job started 1/2 of jobTimeout later
                                else:
                                    '''
                                    This job's time has run out.  Kill the processes and deathNotify singleProcess.
                                    Reset the timestamp and the extensions granted.
                                    this will not become an infinite time extension because singleProcess will give up 
                                    on a job after too many failures.
                                    '''
                                    self.log("Watchdog is killing job " + self.threads[threadId]["ticket"] + " in thread " + \
                                             threadId + " for taking too long.")
                                    self.threads[threadId]["extensions granted"] = 0
                                    self.threads[threadId]["timestamp"] = datetime.datetime.now()
                                    
                                    utils.kill(self.threads[threadId]["processes"], self.server.waitMutex)
                                    #restarting a thread takes so long that it makes sense to refresh information about the threads
                                    processes = utils.checkProcesses( self.threads, self.server.waitMutex )
                #in case removeThread() was called while watchdog was running
                except KeyError:
                    pass
            #release the mutex so that runScript can deal with its dead child
            self.threadsMutex.release()
            
    def clear(self):
        self.readyToExit = True
        self.server = None
        self.log("Watchdog shutting down...")
        
    def blackStork(self):
        '''
        This function calls a non-blocking wait on the direct children of the server.
        Returns a list of process IDs which have died without having been wait()ed for
        Any call to subprocess or Popen which depends on the returned value of the process it starts
            must LOCK the server.waitMutex before starting the process.  This is because
            the exit status of a process can only be retrieved once, and without setting that mutex,
            this function may absorb the necessary information.
        This function is needed because when child processes terminate but aren't wait()ed for, they
            become Zombie processes which take up memory but don't do anything useful.
        '''
        #Handle dying children.
        #this loop's condition will be tested on init or when all of the children have died, be it because the server's shutting down
        #or because all child processes have crashed and none have yet been restarted
        deadChildren = []
        while True:
            self.server.waitMutex.acquire()
            
            try:
                pid, exit = os.waitpid(-1, os.WUNTRACED | os.WNOHANG) #look for the death of a direct child of this process
            except OSError, (value, message):
                if value == 10:
                    pid = 0
                else:
                    raise OSError(value, message)
                
            self.server.waitMutex.release() # waitMutex needs to be released before calling dropProcesses to prevent a deadlock
                                            # because otherwise this function would have both waitMutex and executionMutex(through
                                            # deathNotify(), and at the same time runScript.ooScriptRunner.execute() uses both the 
                                            # waitMutex and the executionMutex
            
            if pid == 0:
                break
            deadChildren.append( str(pid) )
            self.log("Child " + str(pid) + " has died.", 'error\t')
        
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
            self.log("watchdog failed to remove threadId '" + threadId + "' because it is not in its list.", 'error\t')
        except Exception, (message):
            self.log("watchdog failed to remove threadId '" + threadId + "': " + str(message), 'error\t' )
        else:
            self.log("watchdog removed thread " + threadId)
            
        self.threadsMutex.release()
        
    def addThread(self, threadId, processes=[], ticketNumber='ready'):
        '''
        add the thread to watchdog's list.
        Optionally include processes to watch over, and include the thread's status or which job it's working on.
        '''
        self.threadsMutex.acquire()
        self.threads[threadId] = {} #define a key for the thread in watchdog's list
        self.threadsMutex.release()
        
        self.log("watchdog added thread " + threadId)
            
        self.updateThread(threadId=threadId, processes=processes, ticket=ticketNumber, extensionsGranted=0)
        
    def updateThread(self, threadId, processes=None, ticket=None, extensionsGranted=None):
        '''
        Update watchdog's self.threads dictionary entry for thread *threadId*, 
        only changing variables that are passed in:
            processes for "processes", ticket for "ticket", extensionsGranted for "extensions granted"
            
        If a ticket is passed, reset the CPU usage sum and set the timestamp to right now
        '''
        self.threadsMutex.acquire()
        
        #only update the thread's status if the argument is not the keyword None
        if not ticket is None:
            self.threads[threadId]["ticket"] = ticket
            self.threads[threadId]["cpu"] = 0 #if there's a new ticket, reset the cpu usage sum
            self.threads[threadId]["timestamp"] = datetime.datetime.now() #and the timestamp
        #only update the processes list if the argument is not the keyword None
        if not processes is None:
            self.threads[threadId]["processes"] = processes
            
        if not extensionsGranted is None:
            self.threads[threadId]["extensions granted"] = extensionsGranted
        
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
        for threadId in self.threads.keys():
            for watched in self.threads[threadId]['processes']:
                if watched in processes:
                    processes.remove(watched)
                    self.threads[threadId]['processes'].remove(watched)
                    if self.threads[threadId]['processes'] == None: #checkProcesses expects a list (possible empty) of strings; won't work with None
                        self.threads[threadId]['processes'] = []
                    
                    if notifyThread:
                        if not threadId in dropped:
                            dropped[threadId] = []
                        dropped[threadId].append(watched)
              
        self.threadsMutex.release()
        
        #if notifyThread is False, dropped will be empty
        for threadId in dropped:
            self.server.singleProcesses[threadId].deathNotify(dropped[threadId])
        
    
            
            


class jobStatus:
    '''
    This is an enumeration for the status of jobs
    '''
    notFound, error, enqueued, dequeued, done = range(5)
    
class requestHandler(threading.Thread):
    def __init__(self,client, server):
        threading.Thread.__init__(self, name="requestHandler")
        self.client = client
        self.socketBufferSize = server.socketBufferSize
        self.server = server
        self.log = self.server.log
        self.home = "/home/dustymugs/Work/OOo/doos-dustymugs/home/"
        client.setblocking(1)
        client.settimeout(60.0)
        #try to find the remote machine's IP address
        try:
            self.remoteHostName = str( self.client.getpeername() )
        except Exception, (message):
            self.remoteHostName = "-system does not support getpeername()-"

    def run(self):
        try:
            self.log("Client connected from " + self.remoteHostName)
            data_chunks = [] #we're just concatenating the chunks of data received, but this is faster than string concatenation
            buf = self.client.recv(self.socketBufferSize)
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
                    buf = self.client.recv(self.socketBufferSize)  #get more data
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
            args = utils.makeDictionary(argString)
            
            if args.has_key('terminate') and args['terminate']: #guard against "terminate=false"
                try:
                    self.client.sendall( "shutting down...\n" )
                finally:
                    self.log("Received shutdown command from '" + self.remoteHostName + "'.")
                    self.server.terminate() #tell the server to shut down all threads
            
            #if they want to put it in the queue, dump the data to a file and enqueue
            elif args.has_key('prepareJob') and args['prepareJob'] is True:   
                self.prepareJob(argString, data)
            
            #if they want status or they want the job    
            elif ( (args.has_key('stat') and args['stat']) or (args.has_key('returnJob') and args['returnJob']) ) and args.has_key('ticket'):
                logfile, status = self.stat(args['ticket']) #get the file containing the job's status
                
                if status == jobStatus.notFound:
                    self.client.sendall( "STATUS " + str(status) + ": " + str(logfile) )
                    self.log("Sent 'ticket not found' for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.", 'error\t')
                elif (args.has_key('returnJob') and args['returnJob']) and status == jobStatus.done:
                    #this function handles its own logging.
                    self.returnJob( args['ticket'] )
                else:
                    self.client.sendall(logfile)
                    self.log("Sent status for ticket '" + args['ticket'] + "' to '" + self.remoteHostName + "'.")
            else:
                self.client.sendall("STATUS " + jobStatus.error + ": Unknown command\n")
                
                
        except socket.error, (message):
            self.log("Socket error for host '" + self.remoteHostName + "': " + str(message), "error\t" )
        except Exception, (message):
            self.log("Unknown error for host '" + self.remoteHostName + "': " + str(message), 'error\t')
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
                    self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )
                    
        except Exception, (message):
            self.log("Unknown error reading output for ticket " + ticket + ": " + str(message), "error\t" )
        
        #So now we have the data (or failure).  Let's send the data back to the client.
        try:
            if isZip is not None:
                for file in data:
                    self.client.sendall( file[0] + "::file start::" + file[1] + "::fileEnd")
        except socket.error, (message):
            self.log("Socket error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
        except Exception, (message):
            self.log("Unknown error sending output for ticket '" + ticket + "' to '" + self.remoteHostName + "': " + str(message), "error\t" )
        else:
            self.log("Successfully sent output for ticket '" + ticket + "' to '" + self.remoteHostName + "'.")
    
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
        elif logfile.find('timeFailed:') >= 0:
            return logfile, jobStatus.error
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
        file.write('timeEntered:' + datetime.datetime.now().isoformat() + "\n")
        file.close()
        #finally, put the data into the queue
        self.server.jobQueue.put( dirpath, True )
        self.client.sendall( "transmission ok\nticket number:" + filename + "\n")
        self.log("Job '" + filename + "' entered into queue.  Received from '" + self.remoteHostName + "'.")
        
if __name__ == "__main__":
    s = Server()
    s.run()
    #only the main thread can catch signals.  
    
