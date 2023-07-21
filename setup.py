from setuptools import setup,find_packages

setup(name='miniPoly',
      version='0.1.0',
      description='A minimalistic Python package for multipurpose multiprocessing program building',
      author='Yue Zhang',
      author_email='yue.zhang@bi.mpg.de',
      url='https://github.com/nash-yzhang/miniPoly',
      packages=find_packages(where='./miniPoly'),
      classifiers=[
          'Development Status :: 3 - Alpha',
            'Intended Audience :: Neuroscience/Research',
            'Topic :: Scientific software :: Build Tools',
            'License :: OSI Approved :: MIT License',
            'Programming Language :: Python :: 3.9',
            'Programming Language :: Python :: 3.10',
            'Programming Language :: Python :: 3.11',
      ],
      python_requires='>=3.9, <3.12',
      exclude_package_data={'': ['apps', 'external_tools', 'test', '__arc__']},
      )