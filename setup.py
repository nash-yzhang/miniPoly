from setuptools import setup, find_packages
from setuptools.command.develop import develop
from setuptools.command.install import install
import subprocess
import sys


with open('requirements.txt', encoding='utf-16-le') as rqr:
    pkg_rqr = rqr.read().lstrip('\ufeff').split('\n')


class PostDevelopCommand(develop):
    """Post-installation for development mode."""
    def run(self):
        develop.run(self)
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'vispy'])
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'h5py'])

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'vispy'])
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'h5py'])


setup(name='miniPoly',
      version='0.1.0',
      description='A minimalistic Python package for multipurpose multiprocessing program building',
      author='Yue Zhang',
      author_email='yue.zhang@bi.mpg.de',
      url='https://github.com/nash-yzhang/miniPoly',
      python_requires='>=3.9, <3.12',
      install_requires=pkg_rqr,
      packages=find_packages(where='.', exclude=['__arc__', '__arc__.*',
                                                 'APP', 'APP.*',
                                                 'external_tools', 'external_tools.*',
                                                 'test', 'test.*']),
      include_package_data=True,
      package_data={'': ['*.dll', '*.ico']},
      cmdclass={'develop': PostDevelopCommand,
                'install': PostInstallCommand},
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Neuroscience/Research',
          'Topic :: Scientific software :: Build Tools',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: 3.11',
          'Programming Language :: Python :: 3.12',
      ],
      )

