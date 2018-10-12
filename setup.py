from distutils.core import setup

VERSION = '0.1'

setup(name = 'sisock',
      version = VERSION,
      description = 'SImons Observatory data serving through webSOCKets',
      package_dir = {'sisock': 'sisock'},
      packages = ['sisock',])
