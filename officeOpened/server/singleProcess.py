from Queue import Queue
import sys
import threading
import hashlib
import os
from officeController import runScript

#should only receive a job from the dispatcher when self.job is empty

#officeInstance inherits from Thread
class singleProcess (threading.Thread):
    def __init__(self, threadNumber, jobQueue, server):
        threading.Thread.__init__(self)
        self.server =  server  #doesn't need to be in self.data because the same dispatcher is used by all threads
        self.threadId = threadNumber
        self.jobQueue = jobQueue
    
    def run(self):
        ooScriptRunner = runScript.scriptRunner(self.threadId)
        
        while 1:
            print 'Thread ' + str(self.threadId) + " is at the labor exchange, looking for a yob.\n"
            dirpath, args = self.jobQueue.get(True) #block this thread's execution until it gets something from the queue
            
            #if the server tells the thread to terminate gracefully
            if args == 'terminate':
                print 'Thread ' + str(self.threadId) + ' exiting gracefully...\n'
                self.jobQueue.task_done()
                break
            else:
                ooScriptRunner.execute(dirpath, args)
            
            print 'Thread ' + str(self.threadId) + " GOT A YOB!  Mira: \n-----\n" + dirpath + "\nwith args:\n" + str(args) + '\n-----\n\n'
            os.remove(dirpath) #remove the file now that we're done with it
            self.jobQueue.task_done() #helps the queue keep track of how many jobs are still running
        