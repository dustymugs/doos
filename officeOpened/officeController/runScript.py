'''
TODO: add a property to overwrite any file with the same name, and also delete everything with same name at startup
    When a thread is launched, be sure to nuke the output folder in case any residual files are chilling there.

    When a script is done running, zip it IN THE THREAD'S OUTPUT FOLDER, transfer the zip over the server's output folder, and nuke 
        the thread's output folder.
    
    Change the script loading process so that the corrected script is stored inside the home directory and run from there.  This way,
        if the server crashes while doing the path correction (updating <<OUTDIR>>, that is), it can restart the job with the input still
        intact.
'''

import subprocess
import time
import uno
from com.sun.star.beans import PropertyValue
import os
import signal
from zipfile import ZipFile

class scriptRunner:
    def __init__(self, instanceId, homeDir):
        self.instanceId = instanceId
        self.home = homeDir + "officeOpened" + str(instanceId) + '/'
        
        #create a new OpenOffice process and have it listen on a pipe
        self.childOffice = \
            subprocess.Popen( ('soffice', "-accept=pipe,name=officeOpened" + str(instanceId) + ";urp;", "-headless", "-nofirststartwizard"), 
                                                                            env={ "PATH": os.environ["PATH"], 
                                                                            "HOME": self.home } ) #we need to have several 'homes' to have
                                                                                                    #several OO instances running
        time.sleep(10.0)
        
        # get the uno component context from the PyUNO runtime
        localContext = uno.getComponentContext()
        
        # create the UnoUrlResolver
        self.resolver = localContext.ServiceManager.createInstanceWithContext(
                        "com.sun.star.bridge.UnoUrlResolver", localContext )
        
        
    def __del__(self):
        print 'Murthering ' + str(self.childOffice.pid) + '\n'
        os.kill (self.childOffice.pid, signal.SIGTERM)
    
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
        os.mkdir(self.home + 'output/' + ticketNumber) #all macro output should go here
        file = open(dirpath, 'r+') #open the passed macro
        #now rewrite instances of <<OUTDIR>> in the macro with the output location we want
        pathCorrected = file.read().replace('<<OUTDIR>>', self.home + 'output/' + ticketNumber)
        file.truncate(0) #to make sure we overwrite the file
        file.write(pathCorrected)
        file.close()
        
        # connect to the running office
        self.ctx = self.resolver.resolve( "uno:pipe,name=officeOpened" + str(self.instanceId) + ";urp;StarOffice.ComponentContext" )
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
        print 'executed dispatch\n'
        
        # As quoted from the PyUno tutorial:
        # Do a nasty thing before exiting the python process. In case the
        # last call is a oneway call (e.g. see idl-spec of insertString),
        # it must be forced out of the remote-bridge caches before python
        # exits the process. Otherwise, the oneway call may or may not reach
        # the target object.
        # I do this here by calling a cheap synchronous call (getPropertyValue).
        self.ctx.ServiceManager
        
        #We're done with the macro.  Now try to zip the file. 
        try:
            absoluteRoot = self.home + 'output/' + ticketNumber
            zip = ZipFile(self.home + 'output/' + ticketNumber + '.zip', 'w')
            for root, dirs, files in os.walk(absoluteRoot):
                for filename in files:
                    #find relative root for representation in the zip file
                    (junk, relativeRoot) = root.split(absoluteRoot, 1)
                    zip.write("/".join([root,filename]), relativeRoot + filename)
            #if the zip was successful, move it to homeDirectories/output/ticketNumber/files.zip
            os.rename(self.home + 'output/' + ticketNumber + '.zip', self.home + '../files/output/' + ticketNumber + '/files.zip')
        except Exception, (message):
            print "Error writing zip file:\n" + str(message) + "\nMoving output folder instead.\n"
            #move the output files into the server-wide output folder, homeDirectories/output/ticketNumber/files
            os.rename(self.home + 'output/' + ticketNumber, self.home + '../files/output/' + ticketNumber + '/files')
            
        
        print 'done'
        
        
if __name__ == '__main__':
    juno = scriptRunner(2)
    juno.execute('this was a triumph', 321)