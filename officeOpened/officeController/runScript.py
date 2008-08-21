'''
TODO: add a property to overwrite any job with the same name, and also delete everything with same name at startup
    When a thread is launched, be sure to nuke the output folder in case any residual files are chilling there.
    
    MAJOR SECURITY FLAW:  MUST PREVENT STARBASIC SHELL COMMAND FROM RUNNING!  It's available to OO macros

    When a script is done running, zip it IN THE THREAD'S OUTPUT FOLDER, transfer the zip over the server's output folder, and nuke 
        the thread's output folder.
    
    Change the script loading process so that the corrected script is stored inside the home directory and run from there.  This way,
        if the server crashes while doing the path correction (updating <<OUTDIR>>, that is), it can restart the job with the input still
        intact.
        
    Figure out how to tell whether OO crashed while processing a job
'''

import subprocess
import time
import datetime
import uno
from com.sun.star.beans import PropertyValue
import os
import shutil
import zipfile
from server import officeOpenedUtils
import threading

class scriptRunner:
    def __init__(self, instanceId, homeDir, waitMutex):
        self.instanceId = instanceId
        self.home = homeDir + "officeOpened" + str(instanceId) + '/'
        self.shuttingDown = False
        self.waitMutex = waitMutex
        self.executionMutex = threading.Lock()
        self.maxDispatchAttempts = 2
        
        self.startOO()
        
    def startOO(self):
        
        #create a new OpenOffice process and have it listen on a pipe
        self.childOffice = \
            subprocess.Popen( ('soffice', "-accept=pipe,name=officeOpenedPipe" + str(self.instanceId) + ";urp;", "-headless", "-nofirststartwizard"), 
                                                                            env={ "PATH": os.environ["PATH"], 
                                                                            "HOME": self.home } ) #we need to have several 'homes' to have
                                                                                                    #several OO instances running
        time.sleep(2.5)
        
        #OOo spawns a child process which we'll have to look out for.
        #now get the child process which has been spawned (need to kill -9 it in case anything goes wrong)
        print "about to look for children of thread " + str(self.instanceId) + " with ppid= " + str(self.childOffice.pid) + "\n"
        self.grandchildren = []
        #acquire the right to call wait()
        self.waitMutex.acquire()
        ps = subprocess.Popen(("ps", "--no-headers", "--ppid", str(self.childOffice.pid), "o", "pid"), \
                                        env={ "PATH": os.environ["PATH"]}, stdout=subprocess.PIPE)
        psOutput = ps.communicate()[0]
        #release the wait mutex
        self.waitMutex.release()
        for child in psOutput.split("\n")[:-1]: #the last element will be '' so drop it
            self.grandchildren.append(child.lstrip()) #needs to be a string rather than an int. Remove leading whitespace.
            
        print "done looking for children of thread " + str(self.instanceId) + ", found: '" + str(self.grandchildren) + "'\n\n"

        
        # get the uno component context from the PyUNO runtime
        localContext = uno.getComponentContext()
        
        # create the UnoUrlResolver
        self.resolver = localContext.ServiceManager.createInstanceWithContext(
                        "com.sun.star.bridge.UnoUrlResolver", localContext )
        
    def deathNotify(self, deadChildren):
        '''
        Called when the watchdog detects the death of the child office process.  This function waits until any pending job's execute()
        procedure is finished before restarting Open Office.
        self.execute() will determine whether or not the OOo instance crashed during the job, so deathNotify competes with execute() for
        the executionMutex.
        '''
        currentChildrenDead = False
        familyTree = self.getPIDs()
        
        # we only want to restart if the reported dead child is still one we care about,
        # since execute() can restart the office instance on its own if it sees that the instance is dead.
        for deadbaby in deadChildren:
            if deadbaby in familyTree:
                print "deathNotify can't stop thinking about executionMutex\n"
                self.executionMutex.acquire()
                
                officeOpenedUtils.kill( self.getPIDs(), self.waitMutex )   
                self.startOO()
                print "deathNotify doesn't even care about execution"
                self.executionMutex.release()
                print "Mutex anymore.\n"
                
                break
            
        
        
    def getPIDs(self):
        '''
        Returns string representations of the PIDs OpenOffice instance spawned by this thread and any direct children that instance may have.
        '''
        return [str(self.childOffice.pid)] + self.grandchildren
    
    def execute(self, dirpath, args):
        '''
        Create a folder in this thread's home directory/output named after the ticket number of the current job.  This folder will contain 
            any output files produced by the macro.  Search through the macro file and replace any instances of <<OUTDIR>> with the place
            we want the script to send output, which is the ticket folder we created.
        Grab the script located at dirpath, then connect to OpenOffice and run it.
        When done, move the folder we created to the program folder/files/output
        '''
        (junk, ticketNumber) = dirpath.rsplit('/', 1) #the ticket number is what's at the end of the path to the input file
        ticketNumber = str(ticketNumber)
        
        if not args.has_key('initFunc'):
            raise Exception( "initFunc was not defined by client for ticket " + ticketNumber + "\n" )
        
        dirpath += '.data' #add .data to the end of the ticket number to get the macro's filename
        file = open(dirpath, 'r+') #open the passed macro
        #now rewrite instances of <<OUTDIR>> in the macro with the output location we want
        pathCorrected = file.read().replace('<<OUTDIR>>', self.home + 'output/' + ticketNumber)
        file.truncate(0) #to make sure we overwrite the file
        file.write(pathCorrected)
        file.close()
        
        executionSuccess = False
        #make two attempts at execution
        i = 1
        while (i <= self.maxDispatchAttempts):
            #prevent OO from being restarted by anyone else
            self.executionMutex.acquire()
            try:
                # connect to the running office
                self.ctx = self.resolver.resolve( "uno:pipe,name=officeOpenedPipe" + str(self.instanceId) + ";urp;StarOffice.ComponentContext" )
                print 'connected\n'
                
                # get the central desktop object
                self.desktop = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.Desktop",self.ctx)
                print 'got central desktop object\n'
            
                self.dispatchHelper = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.DispatchHelper", self.ctx )
                print 'created dispatch helper\n'
                
                properties = []
                p = PropertyValue()
                p.Name = "junk"
                p.Value = 'in the trunk'
                properties.append(p)
                properties = tuple(properties)
        
                self.dispatchHelper.executeDispatch(self.desktop, 'macro:///AutoOOo.OOoCore.runScript(' + dirpath + ',' \
                                                     + args["initFunc"] + ')', "", 0, properties) 
                print 'executed dispatch\nPerforming final UNO call. Current time: ' + datetime.datetime.utcnow().isoformat() + "\n"
                
                # As quoted from the PyUno tutorial:
                # Do a nasty thing before exiting the python process. In case the
                # last call is a oneway call (e.g. see idl-spec of insertString),
                # it must be forced out of the remote-bridge caches before python
                # exits the process. Otherwise, the oneway call may or may not reach
                # the target object.
                # I do this here by calling a cheap synchronous call (getPropertyValue).
                self.ctx.ServiceManager
                
                print 'finished final UNO call at ' + datetime.datetime.utcnow().isoformat() + "\n"
            #if OpenOffice crashed
            except Exception, (message):
                print "Open Office crashed (message: " + str(message) + ") during execution of job number " + \
                    ticketNumber + ".  " + str(self.maxDispatchAttempts - i) + " attempt(s) remaining before job is abandoned.\n"
                #only the PIDs which this iteration of the loop started with can be returned by getPIDs, because 
                #execute() has the executionMutex, which is necessary for deathNotify() to restart OO.
                officeOpenedUtils.kill( self.getPIDs(), self.waitMutex )
                self.startOO()
                i += 1
                #if OO died because watchdog killed it, watchdog is probably in runScript.deathNotify(), which is waiting for  
                #executionMutex. Give it a chance to complete its calls and start monitoring again before re-acquiring the mutex.
                self.executionMutex.release()
                continue
            
            #else if there was no exception....
            else:
                #We're done with the macro.  Now try to zip the file. 
                try:
                    absoluteRoot = self.home + 'output/' + ticketNumber
                    zip = zipfile.ZipFile(self.home + 'output/' + ticketNumber + '.zip', 'w', zipfile.ZIP_DEFLATED, True)
                    for root, dirs, files in os.walk(absoluteRoot):
                        for filename in files:
                            #find relative root for representation in the zip file
                            (junk, relativeRoot) = root.split(absoluteRoot, 1)
                            zip.write("/".join([root,filename]), relativeRoot + filename)
                    #if the zip was successful, move it to homeDirectories/output/ticketNumber/files.zip
                    shutil.move(self.home + 'output/' + ticketNumber + '.zip', self.home + '../files/output/' + ticketNumber + '/files.zip')
                except Exception, (message):
                    print "Error writing zip file:\n" + str(message) + "\nMoving output folder instead.\n"
                    #move the output files into the server-wide output folder, homeDirectories/output/ticketNumber/files
                    shutil.move(self.home + 'output/' + ticketNumber, self.home + '../files/output/' + ticketNumber + '/files')
        
                print 'done'
            executionSuccess = True
            #we won't get here if the job failed too many times because of the continue statement, so we don't need to worry about 
            self.executionMutex.release() #releasing the lock when it isn't locked.
            break #if we made it this far, Open Office didn't crash, so we don't need to re-try.
        
        return executionSuccess
    
        
        
if __name__ == '__main__':
    juno = scriptRunner(2)
    juno.execute('this was a triumph', 321)