'''
TODO: add a property to overwrite any file with the same name, and also delete everything with same name at startup
'''

import subprocess
import time
import uno
from com.sun.star.beans import PropertyValue
import os

class howdy:
    def __init__(self, instanceId):
        self.instanceId = instanceId
        self.home = "/home/clint/officeOpened/homeDirectories/officeOpened" + str(instanceId)
        
        #create a new OpenOffice process and have it listen on a pipe
        subprocess.Popen( ('soffice', "-accept=pipe,name=officeOpened" + str(instanceId) + ";urp;", "-headless", "-nofirststartwizard"), 
                                                                            env={ "PATH": os.environ["PATH"], 
                                                                            "HOME": self.home } ) #we need to have several 'homes' to have
                                                                                                    #several OO instances running
        time.sleep(10.0)
        
        # get the uno component context from the PyUNO runtime
        localContext = uno.getComponentContext()
        
        # create the UnoUrlResolver
        resolver = localContext.ServiceManager.createInstanceWithContext(
                        "com.sun.star.bridge.UnoUrlResolver", localContext )
        
        # connect to the running office
        self.ctx = resolver.resolve( "uno:pipe,name=officeOpened" + str(self.instanceId) + ";urp;StarOffice.ComponentContext" )
        print 'connected\n'
        # get the central desktop object
        self.desktop = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.Desktop",self.ctx)
        print 'got central desktop object\n'
    
        self.dispatchHelper = self.ctx.ServiceManager.createInstanceWithContext( "com.sun.star.frame.DispatchHelper", self.ctx )
        print 'created dispatch helper\n'
        
    
    def makeAndSave(self, content, jobId):
        
        properties = []
        p = PropertyValue()
        p.Name = "bob"
        p.Value = 'macro:///AutoOOo.OOoCore.runScript\(/home/clint/OOo/sample.script,Main\)'
        properties.append(p)
        properties = tuple(properties)

        self.dispatchHelper.executeDispatch(self.desktop, 'macro:///AutoOOo.OOoCore.runScript(/home/clint/OOo/sample.script,Main)', "", 0, properties) 
        print 'executed dispatch\n'
        

        # Do a nasty thing before exiting the python process. In case the
        # last call is a oneway call (e.g. see idl-spec of insertString),
        # it must be forced out of the remote-bridge caches before python
        # exits the process. Otherwise, the oneway call may or may not reach
        # the target object.
        # I do this here by calling a cheap synchronous call (getPropertyValue).
        self.ctx.ServiceManager
        print 'done'
        
if __name__ == '__main__':
    juno = howdy(2)
    juno.makeAndSave('this was a triumph', 321)