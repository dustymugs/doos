doos is a multi-threaded network server designed for running client-provided macros on multiple LibreOffice instances simultaneously.  doos was designed from the beginning to be used by a web server to generate reports dynamically. It is intended to take advantage of a multi-core system, but will work on uniprocessor systems as well.

On startup, the server will spawn a configurable number of LibreOffice processes and constantly monitor them for hanging, crashes, and excessive job processing time.  LibreOffice Basic macro files can be sent over the network, and will be queued as jobs.  Each job has a ticket number.  Clients can request the status of a job at any time, and have the output of the job sent to them in a zip file upon completion.

This program is always a work in progress.  It performs all of the above functions, but the protocol for communication with the server is fully functional but isn't based on a standard defined from outside the project.  Rather communication is done over raw TCP sockets.  The eventual plan is to add an cgi script that communicates over HTTP w/ XML, thus allowing browsers to directly connect to the server.

To use doos, please export svn/trunk with the following:

`svn export http://doos.googlecode.com/svn/trunk/ doos`