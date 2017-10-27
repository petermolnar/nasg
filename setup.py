from setuptools import setup, find_packages
from . import __version__

setup(
    version=__version__,
    name="nasg",
    author="Peter Molnar",
    author_email="hello@petermolnar.eu",
    description="Not Another Static Generator - a static generator",
    long_description=open('README.md').read(),
    packages=['nasg'],
    install_requires=['arrow', 'Jinja2', 'langdetect', 'requests', 'requests-oauthlib', 'sanic', 'unicode-slugify', 'Wand', 'emoji', 'html5lib', 'BeautifulSoup'],
    url='https://github.com/petermolnar/nasg',
    license=open('LICENCE').read(),
    include_package_data=True,
)
