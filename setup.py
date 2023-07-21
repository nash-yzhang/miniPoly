from setuptools import setup, find_packages

with open('requirements.txt', encoding='utf-16-le') as rqr:
    pkg_rqr = rqr.read().lstrip('\ufeff').split('\n')

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
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Neuroscience/Research',
          'Topic :: Scientific software :: Build Tools',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: 3.11',
      ],
      )
