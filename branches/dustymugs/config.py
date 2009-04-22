'''
doos: A multi-threaded server for running client-provided macros in OpenOffice.org
Copyright (C) 2008 - 2009  therudegesture and dustymugs

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, a copy is available at
http://www.gnu.org/licenses/gpl-3.0-standalone.html
'''

import os, sys

# default application config filename
iniDefault = 'config.ini.default'
# user application config filename
iniUser = 'config.ini'
# search paths for application config files
iniPaths = ['/etc/', '/usr/local/etc/', './']

# load the config files
def load(cfg):
	# search for default config
	for x in iniPaths:
		if os.path.exists(x + iniDefault):
			cfg.read(x + iniDefault)
			break

	# search for user config
	for x in iniPaths:
		if os.path.exists(x + iniUser):
			cfg.read(x + iniUser)
			break
