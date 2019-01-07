import versioneer

from distutils.core import setup

setup(name = 'sisock',
      version = versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      description = 'SImons Observatory data serving through webSOCKets',
      package_dir = {'sisock': 'sisock'},
      packages = ['sisock',])
