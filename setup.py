from setuptools import setup, find_packages
from setuptools.command.install import install as _install
from setuptools.command.develop import develop as _develop
import os


def _post_install(libname, libpath):
    from js9 import j
    # add this plugin to js9 config
    c = j.core.state.configGet('plugins', defval={})
    c[libname] = "%s/github/0-complexity/0-access" % j.dirs.CODEDIR
    j.core.state.configSet('plugins', c)
    j.tools.jsloader.generate()


class install(_install):
    def run(self):
        _install.run(self)
        libname = self.config_vars['dist_name']
        libpath = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), libname)
        self.execute(_post_install, (libname, libpath),
                     msg="Running post install task")


class develop(_develop):
    def run(self):
        _develop.run(self)
        libname = self.config_vars['dist_name']
        libpath = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), libname)
        self.execute(_post_install, (libname, libpath),
                     msg="Running post install task")


long_description = ""
try:
    from pypandoc import convert
    long_description = convert('README.md', 'rst')
except ImportError:
    long_description = ""

with open("requirements.txt", encoding="utf-8") as file:
    requirements = [l.strip() for l in file]

setup(
    name='JumpScale9ZeroAccess',
    version='1.0.0',
    description='Itsyou.online authenticated and monitored ssh access via web',
    long_description=long_description,
    url='https://github.com/0-complexity/0-access',
    author='GreenItGlobe',
    author_email='info@gig.tech',
    license='Apache',
    packages=find_packages(),
    install_requires=requirements,
    cmdclass={
        'install': install,
        'develop': develop,
        'development': develop,
    },
)
