# used by requestHandler
class jobStatus:
	'''
	This is an enumeration for the status of jobs
	'''
	notFound, error, enqueued, dequeued, done = range(5)
