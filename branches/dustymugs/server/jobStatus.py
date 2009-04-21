# used by requestHandler
class jobStatus:
	'''
	This is an enumeration for the status of jobs
	'''
	notFound, error, enqueued, dequeued, done = range(5)

	def asText(id):
		if id == 0:
			rtn = 'Not found'
		elif id == 1:
			rtn = 'Error'
		elif id == 2:
			rtn = 'Enqueued'
		elif id == 3:
			rtn = 'Dequeued'
		elif id == 4:
			rtn = 'Done'
		else:
			rtn = false
		return rtn

	asText = staticmethod(asText)
