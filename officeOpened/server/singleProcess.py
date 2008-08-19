from Queue import Queue
import sys
import threading
import hashlib
import os
import signal
from server import officeOpenedUtils
from officeController import runScript
import datetime

home = '/home/clint/officeOpened/homeDirectories/'

#should only receive a job from the dispatcher when self.job is empty

#officeInstance inherits from Thread
class singleProcess (threading.Thread):
    def __init__(self, threadNumber, jobQueue, watchdog, waitMutex):
        threading.Thread.__init__(self, name="singleProcess" + threadNumber)
        self.threadId = threadNumber
        self.jobQueue = jobQueue
        self.ooScriptRunner = runScript.scriptRunner(self.threadId, home, waitMutex)
        self.watchdog = watchdog
        self.waitMutex = waitMutex #prevents self.watchdog.blackStork() from robbing calls to outside programs of their exit status
        self.myKidsMutex = threading.Lock() #prevents conflicts between getPIDs() and deathNotify()
        self.shuttingDown = False
    
    def run(self):

        while 1:
            print 'Thread ' + str(self.threadId) + " is at the labor exchange, looking for a yob.\n"
            dirpath = self.jobQueue.get(True) #block this thread's execution until it gets something from the queue
            
            #if the server tells the thread to terminate gracefully
            if dirpath == 'terminate':
                print 'Thread ' + str(self.threadId) + ' exiting gracefully...\n'
                self.jobQueue.task_done()
                self.clear()
                break
            else:
                #read the arguments from the .args file for this ticket
                file = open(dirpath + '.args', 'r')
                args = file.read()
                file.close()
                args = officeOpenedUtils.makeDictionary(args)
                # now get the ticket number
                (junk, ticketNumber) = dirpath.rsplit('/', 1) #the ticket number is what's at the end of the path to the input file
                #now write the time that the file was taken out of the queue
                file = open(home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')
                file.write('timeDequeued:' + datetime.datetime.utcnow().isoformat() + "\n")
                file.close()
                #execution stage
                success = self.ooScriptRunner.execute(dirpath, args)
                #write the job's status to status.txt now that it's done
                file = open(home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')
                
                if success:
                    file.write('timeCompleted:')
                else:
                    file.write('timeFailed:')
                
                file.write( datetime.datetime.utcnow().isoformat() + "\n" )
                file.close()
                #remove the file now that we're done with it
                os.remove(dirpath + '.data') 
                os.remove(dirpath + '.args')
            
            self.jobQueue.task_done() #helps the queue keep track of how many jobs are still running
            
    def deathNotify(self, deadKids):
        '''
        When one of the processes registered by this thread to the watchdog dies and is caught by the watchdog (through 
        SIGCHLD from the system), the watchdog will pass the list of dead processes to this function.  This function grabs 
        the myKidsMutex to block getPIDs() calls temporarily, and passes the dead kids notification on to the implemented 
        process handler.  It will then update the watchdog's process list for this thread.
        
        The function will do nothing if self.clear() has been run (and we are therefore shutting down).
        '''
        if not self.shuttingDown:
            self.myKidsMutex.acquire()
            newProcessList = self.ooScriptRunner.deathNotify(deadKids)
            self.myKidsMutex.release()
            
            self.watchdog.updateProcesses( self.threadId, self.getPIDs() )
 
    def getPIDs(self):
        '''
        Returns a list of strings of the process id of the parent process spawned by the thread followed by those of any 
        child processes spawned by that process.  Like so:
        ["123", "4325", "2342"]
        '''
        #use the myKidsMutex so that deathNotify doesn't screw with this
        self.myKidsMutex.acquire()
        
        myKids = self.ooScriptRunner.getPIDs()
        
        self.myKidsMutex.release()
        return myKids
    
    def clear(self):
        '''
        Pre-destructor code to:
            break circular references between the watchdog and the thread
            kill child processes
        '''
        self.shuttingDown = True
        #get the PIDs of the processes associated with this thread
        pids = self.getPIDs()
        #and kill them all

        officeOpenedUtils.kill([pids], self.waitMutex)
        self.server = None
        self.watchdog.removeThread(self.threadId)