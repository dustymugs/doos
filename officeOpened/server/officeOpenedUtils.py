'''
Utility functions for officeOpened and its components
'''

import time
import subprocess
import os
import signal

def makeDictionary(argString):
    '''
    turn a string which was formatted like so: 
    key1=value1;key2=value2;key3;key4;key5=value5
    into a dictionary
    '''
    #split up the arguments if there are several, and put them into key/value pairs
    splitArgs = argString.split(";")
    args={} #args is now a dictionary
    
    for arg in splitArgs:
        arg = arg.split("=", 1)
        if len(arg) is 1: #for value-less arguments like ("terminate")
            args[ arg[0] ] = True #assign them the value of True
        else:
            args[ arg[0] ] = arg[1]
    return args

def checkProcesses(groups, waitMutex):
    '''
    Generate a dictionary of collective CPU usage for each thread's processes
    Expects a dictionary "groups" of the form:
        [
            1: ['132', '2133', '1231'],
            2: ['34', '2435'],
            0: ['345', '55', '345', '3455']
        ]
            ...where the key is the thread id according to singleProcess.py
    
    Returns a similar dictionary, but CPU usage is given as a percentage of total CPU time, followed by associated PIDs:
        [
            1: [ 22, ['132', '2133', '1231'] ],
            2: [ 12, ['34', '2435'] ],
            0: [ 1, ['345', '55', '345', '3455'] ]
        ]
            
    '''
    pidString = ""
    threads = {}
    ownerOf = {} #pairs a Process ID with the thread it belongs to
    
    print "checkProcesses got: " + str(groups) + "\n"
    
    for threadId in groups.keys():
        PIDs = groups[threadId]
        #start creating the hierarchy
        threads[threadId] = [ 0.0, PIDs ] #each thread has an entry of (CPU usage, process IDs)
        pidString += ",".join(PIDs) + ','
        for process in PIDs:
            ownerOf[process] = threadId
            
    pidString = pidString[:-1] #remove that trailing ','
    
    if len(pidString) > 0:
        #acquire the right to wait
        waitMutex.acquire()
        #output the PID and CPU usage of the processes in threadString
        ps = subprocess.Popen(("ps", "S", "--no-headers", "o", "pid,pcpu", "--pid", pidString), stdout=subprocess.PIPE)
        processStrings = ps.communicate()[0].split("\n") #make a list of strings with PID and CPU usage
        #release the wait mutex
        waitMutex.release()
        
        #now run through the result of ps and add each process's cpu usage to its thread's total
        for process in processStrings[:-1]: #the last item of processStrings will be '' so drop it
            pid, cpu =  process.split(None, 2)
            pid = pid.lstrip() #get rid of leading whitespace
            threads[ ownerOf[pid] ]  [0] += float(cpu) #adds to the cpu usage of that PID's thread
        
    return threads;

def kill(drunkards, waitMutex):
    '''
    Kill the passed processes in the same way that people at Froggy's deal with drunkards at closing time:
        Politely ask the drunkard to leave by giving him SIGTERM, and assume that he'll have the good graces
            to take his clique with him.
        Give him 3 seconds to get out
        If he's still there after three seconds, kill him and his little friends with SIGKILL
        
    Expects a list of threads whose processes are to be killed, with the parent process id at the head of each list:
        [
            [ "2300", "2321", "3424" ],  #2300 is the parent process id of this thread
            [ "864", "8668", "3838" ],    #864 is the parent process id of this thread
            [ "483", "4383", "3483" ]    #483 is the parent process id of this thread
        ]
    '''
    checkList = [] #this list will be join()'d and passed to ps as the PIDs to investigate
    for clique in drunkards:
        drunkard = clique[0] #the first member of each list is the parent process
        print "SIGTERM:\t" + drunkard + "\n"
        try:
            checkList.append(drunkard)
            os.kill ( int(drunkard), signal.SIGTERM ) #politely ask the drunkard to leave and take his friends with him
        except OSError, (value, message):
            if value == 3: #the drunkard has already left
                print "Notice: process " + drunkard + " is already dead.\n"
                checkList.remove(drunkard) #if he's already gone, scratch him off your list
            else:
                print "Unknown OSError while attempting to shutdown process " + drunkard + ": " + message + "\n"
        except Exception, (message):
            print "Unknown exception while attempting to shutdown process " + drunkard + ": " + str(message) + "\n"
        finally:
            checkList += clique[1:]
            
    print "\n"
    
    #now give them 3 seconds to get out
    time.sleep(3)
    
    #don't do all this if there are no processes to worry about
    if len(checkList) > 0:
        #acquire the right to call wait()
        waitMutex.acquire()
        #TODO: modify this so that we call waitpid() for the ones we're interested in instead of ps
        #check to see if any drunkards are still lingering (by running ps and passing it the list of process IDs)
        ps = subprocess.Popen( ("ps", "--no-headers", "o", "pid", "--pid", ",".join(checkList) ), stdout=subprocess.PIPE)
        lingeringDrunkards = ps.communicate()[0].split("\n") #make a list of PIDs which are still alive
        #release the wait mutex
        waitMutex.release()
        
        for drunkard in lingeringDrunkards[:-1]: #the last item of lingeringDrunkards = ''
            print "SIGKILL:\t" + drunkard + "\n"
            try:
                os.kill ( int(drunkard), signal.SIGTERM ) #politely ask the drunkard to leave
            except OSError, (value, message):
                if value == 3: #the drunkard has already left
                    print "Notice: process " + drunkard + " is already dead; no SIGKILL necessary.\n"
                else:
                    print "Unknown OSError while attempting to SIGKILL process " + drunkard + ": " + message + "\n"
            except Exception, (message):
                print "Unknown exception while attempting to SIGKILL process " + drunkard + ": " + str(message) + "\n"
            
    print "\n"