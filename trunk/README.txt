SUMMARY

doos (Document OpenOffice.org Server) is a multi-threaded network server designed for running client-provided macros on multiple OpenOffice.org instances simultaneously. doos was designed from the beginning to be used by a web server to generate reports dynamically. It is intended to take advantage of a multi-core system, but will work on uniprocessor systems as well.

On startup, the server will spawn a configurable number of OpenOffice.org processes and constantly monitor them for hanging, crashes, and excessive job processing time. OpenOffice.org Basic macro files can be sent over the network, and will be queued as jobs. Each job has a ticket number. Clients can request the status of a job at any time, and have the output of the job sent to them in a zip file upon completion.

This program is in an ALPHA stage. It performs all of the above functions, but the protocol for communication with the server is fully functional but isn't based on a standard defined from outside the project. This issue may be corrected eventually.
