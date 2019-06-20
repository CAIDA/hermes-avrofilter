#!/usr/bin/env/python
#

from setuptools import setup, find_packages

setup(name="avrofilter",
        version="1.0.0",
        description="Swift middleware for removing sensitive fields from Avro data",
        url="https://github.com/CAIDA/",
        author="Shane Alcock",
        author_email="shane.alcock@waikato.ac.nz",
        license="Apache 2.0",
        packages=find_packages(),
        install_requires=['swift', 'avro_streamer'],
        entry_points={'paste.filter_factory':
                ['avrofilter=avrofilter.avrofilter:filter_factory']}
)

