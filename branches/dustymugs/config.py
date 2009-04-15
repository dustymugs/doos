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
