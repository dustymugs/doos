'''
TODO: add a property to overwrite any file with the same name, and also delete everything with same name at startup
'''

import subprocess
import time
import uno
import os

class howdy:
    def __init__(self, instanceId):
        self.fileExtension = ".odt"
        self.instanceId = instanceId
        self.home = "/home/clint/officeOpened/homeDirectories/officeOpened0"
        self.service = "private:factory/swriter"
        
        #create a new OpenOffice process and have it listen on a pipe
        subprocess.Popen( ('soffice', "-accept=pipe,name=officeOpened" + str(self.instanceId) + ";urp;", "-headless", "-nofirststartwizard"), 
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
    
    def makeAndSave(self, content, jobId):
        self.document = self.desktop.loadComponentFromURL( self.service, "_blank", 0, () )
        print 'created the current document\n'
        # access the current writer document
        #document = desktop.getCurrentComponent()
        
        # access the document's text property
        text = self.document.Text
        print "got the document\'s text property\n"
        # create a cursor
        cursor = text.createTextCursor()
        print 'created a cursor\n'
        # insert the text into the document
        text.insertString( cursor, content, 0 )
        print 'inserted string\n'
        
        fileExtension = '.odt'
        self.document.storeToURL( 'file:///home/clint/officeOpened/homeDirectories/officeOpened' + str(self.instanceId) + '/' \
                                  +  str(jobId) + self.fileExtension, () )
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