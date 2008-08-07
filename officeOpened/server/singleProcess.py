from Queue import Queue
import sys
import threading
import hashlib
import os
from officeController import runScript
import datetime

home = '/home/clint/officeOpened/homeDirectories/'

#should only receive a job from the dispatcher when self.job is empty

#officeInstance inherits from Thread
class singleProcess (threading.Thread):
    def __init__(self, threadNumber, jobQueue, server):
        threading.Thread.__init__(self)
        self.server =  server  #doesn't need to be in self.data because the same dispatcher is used by all threads
        self.threadId = threadNumber
        self.jobQueue = jobQueue
    
    def run(self):
        ooScriptRunner = runScript.scriptRunner(self.threadId, home)
        
        while 1:
            print 'Thread ' + str(self.threadId) + " is at the labor exchange, looking for a yob.\n"
            dirpath = self.jobQueue.get(True) #block this thread's execution until it gets something from the queue
            
            #if the server tells the thread to terminate gracefully
            if dirpath == 'terminate':
                print 'Thread ' + str(self.threadId) + ' exiting gracefully...\n'
                self.jobQueue.task_done()
                break
            else:
                #read the arguments from the .args file for this ticket
                file = open(dirpath + '.args', 'r')
                args = file.read()
                file.close()
                # now get the ticket number
                (junk, ticketNumber) = dirpath.rsplit('/', 1) #the ticket number is what's at the end of the path to the input file
                #now write the time that the file was taken out of the queue
                file = open(home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')
                file.write('\ntimeDequeued:' + datetime.datetime.utcnow().isoformat())
                file.close()
                #execution stage
                ooScriptRunner.execute(dirpath, args)
                #write the job's status to status.txt now that it's done
                file = open(home + 'files/output/' + str(ticketNumber) + '/status.txt', 'a')
                file.write('\ntimeCompleted:' + datetime.datetime.utcnow().isoformat())
                file.close()
                #remove the file now that we're done with it
                os.remove(dirpath + '.data') 
                os.remove(dirpath + '.args')
            print 'Thread ' + str(self.threadId) + " GOT A YOB!  Mira: \n-----\n" + dirpath + "\nwith args:\n" + str(args) + '\n-----\n\n'
            
            self.jobQueue.task_done() #helps the queue keep track of how many jobs are still running
        