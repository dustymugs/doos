from Queue import Queue
import sys
import threading
import hashlib
#from officeController.helloUno import howdy

#should only receive a job from the dispatcher when self.job is empty

#officeInstance inherits from Thread
class singleProcess (threading.Thread):
    def __init__(self, threadNumber, jobQueue, server):
        threading.Thread.__init__(self)
        self.server =  server  #doesn't need to be in self.data because the same dispatcher is used by all threads
        self.threadId = threadNumber
        self.jobQueue = jobQueue
        self.jobId = 10000 * threadNumber
    
    def run(self):
        #ooTest = howdy(self.threadId)
        
        while 1:
            print 'Thread ' + str(self.threadId) + " is at the labor exchange, looking for a yob.\n"
            job = self.jobQueue.get(True) #block this thread's execution until it gets something from the queue
            #if the server tells the thread to terminate gracefully
            if str(job) == 'terminate':
                print 'Thread ' + str(self.threadId) + ' exiting gracefully...\n'
                self.jobQueue.task_done()
                break
            else:
                #first split the job into checksum, inital function name, and macro body
                job = job.split('|', 1) #checksum, initial function name, and macro body are separated by | so we need to split twice here
                initialFunction = job[0]
                macro = job[1]
                #ooTest.makeAndSave(job, self.jobId)
                self.jobId += 1
            
            print 'Thread ' + str(self.threadId) + " GOT A YOB!  Mira: \n-----\n" + str( job ) + " characters\n-----\n\n"
            self.jobQueue.task_done() #helps the queue keep track of how many jobs are still running
        
        
    
    '''
    
    def run(self)
        print 'started thread ' + str(self.threadId) + "\n"
        self.job = False
        
    #requestJob will be called by run when it's ready for a new job.  If there's no new job, it'll terminate,
    #and the dispatcher will call setJob followed by run when it does have a job to give this thread.
    def requestJob(self)
        #TODO: raise an exception if there's already a job here
        if self.job:
            raise Exception("requestJob called while a job was still pending", self.threadId, self.job)
            return False
        
        self.dispatcher.nextJob(self.threadId)
        return True
        
    def setJob(self, job)
        if self.job:
            raise Exception("setJob called while a job was still pending", self.threadId, job, self.job)
            return False
        else:
            self.job = job
            return True
    '''
