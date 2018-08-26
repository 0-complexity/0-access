from setuptools import setup, find_packages
from setuptools.command.install import install as _install
from setuptools.command.develop import develop as _develop
import os


long_description = ""
try:
    from pypandoc import convert
    long_description = convert('README.md', 'rst')
except ImportError:
    long_description = ""

with open("requirements.txt", encoding="utf-8") as file:
    requirements = [l.strip() for l in file]

setup(
    name='zeroaccess',
    version='1.0.0',
    description='Itsyou.online authenticated and monitored ssh access via web',
    long_description=long_description,
    url='https://github.com/0-complexity/0-access',
    author='GreenItGlobe',
    author_email='info@gig.tech',
    license='Apache',
    packages=find_packages(),
    install_requires=requirements,
)
