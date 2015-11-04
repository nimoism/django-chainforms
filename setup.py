from setuptools import setup, find_packages

import chainforms as meta


def long_description():
    with open('README.rst') as f:
        rst = f.read()
        return rst

setup(
    name='django-chainforms',
    version=meta.__version__,
    description=meta.__doc__,
    author=meta.__author__,
    author_email=meta.__contact__,
    long_description=long_description(),
    url='https://github.com/nimoism/django-chainforms.git',
    platforms=["any"],
    packages=find_packages(),
    scripts=[],
    install_requires=[
        'django',
        'django-formtools',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2',
        'Framework :: Django',
        'Topic :: Software Development :: Libraries',
    ]
)