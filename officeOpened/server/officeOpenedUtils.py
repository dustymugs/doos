'''
Utility functions for officeOpened and its components
'''
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