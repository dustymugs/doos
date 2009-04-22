SUMMARY

doos (Document OpenOffice.org Server) is a multi-threaded network server designed for running client-provided macros on multiple OpenOffice.org instances simultaneously. doos was designed from the beginning to be used by a web server to generate reports dynamically. It is intended to take advantage of a multi-core system, but will work on uniprocessor systems as well.

On startup, the server will spawn a configurable number of OpenOffice.org processes and constantly monitor them for hanging, crashes, and excessive job processing time. StarBasic macro files can be sent over the network, and will be queued as jobs. Each job has a ticket number. Clients can request the status of a job at any time, and have the output of the job sent to them in a zip file upon completion.

This program is in an ALPHA stage. It performs all of the above functions, but the protocol for communication with the server is fully functional but isn't based on a standard defined from outside the project. This issue may be corrected eventually.

REQUIREMENTS

- Python 2.4 or newer (Python 3000 has not been tested)
- Java Runtime Environment (needed for pyuno bridge)
- OpenOffice 2.4.2 or newer (OpenOffice 3.0 has not been tested)
	- headless module is required

COMMUNICATION PROTOCOL

By default, the server listens on TCP 8568.

When a client sends a job, he is assigned a ticket number which uniquely identifies the job in the system.
The input sent by the client is stored in [workspace]/files/input/**ticket number**
When the job processing is finished, the job is stored in [workspace]/files/output/**ticket number**

The protocol for all client REQUEST is:

	{NUMBER OF BYTES FOLLOWING THE PIPE}|{SHA1 CHECKSUM OF EVERYTHING FOLLOWING THE PIPE}|{ARGUMENTS}::file start::[{FILE0 NAME}::file content::{FILE0 CONTENT}::file end::[::file start::{FILEX NAME}::file content::{FILEX CONTENT}::file end::]]

	'::file start::', '::file content::' and '::file end::' are tokens

	FILE0 is always the script to run while FILEX is for other files needed by the script

	The ARGUMENTS string coming from the client should be formatted as follows:
		key1=value1;key2=value2;key3;key4;key5=value5  (etc)

	Valid KEYS are:
		terminate
			- instruct the server to shutdown
			- value is OPTIONAL
		prepareJob
			- add new job to server
			- return should be job ticket
			- the key "initFunc" is a dependent argument
				- ex: prepareJob;initFunc=Main
			- value is OPTIONAL
		initFunc
			- value is the name of function to be launched
			- depends upon the key preparejob
			- value is REQUIRED
		returnJob
			- get the output of job using provided ticket
			- response will be the job output
			- the key "ticket" is required
				- ex: returnJob;ticket=123456
			- value is OPTIONAL
		statusJob
			- get the status of job using provided ticket
			- response will be job's status file
			- the key "ticket" is required
				- ex: statusJob;ticket=123456
			- value is OPTIONAL
		deleteJob
			- delete the output files of a job using provided ticket
			- TODO: have command remove job from queue if job not processed yet
			- the key "ticket" is required
				- ex: deleteJob;ticket=123456
			- value is OPTIONAL
		ticket
			- value is REQUIRED

When a client requests a ticket, the system searches the output folder for the ticket as a filename and returns the file if found.
	If that file is not found, but it is found in input/, then the server responds that the job is still being processed
	if that file is not found in either folder, the server replies that the ticket id is unknown

The protocol for any server RESPONSE is:
	{NUMBER OF BYTES FOLLOWING THE PIPE}|{SHA1 CHECKSUM OF EVERYTHING FOLLOWING THE PIPE}|[{SERVER RESPONSE}][::file start::{FILE0 NAME}::file content::{FILE0 CONTENT}::file end::[::file start::{FILEX NAME}::file content::{FILEX CONTENT}::file end::]]

The SERVER RESPONSE follows the following format:
	[OK] MESSAGE
	[ERROR] MESSAGE
