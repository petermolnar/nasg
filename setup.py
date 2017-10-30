from setuptools import setup, find_packages

setup(
    version='2.0.0',
    name="nasg",
    author="Peter Molnar",
    author_email="hello@petermolnar.eu",
    description="Not Another Static Generator - a static generator",
    long_description=open('README.md').read(),
    packages=['nasg'],
    install_requires=[
        'arrow',
        'Jinja2',
        'langdetect',
        'requests',
        'requests-oauthlib',
        'sanic',
        'unicode-slugify',
        'Wand',
        'emoji',
    ],
    url='https://github.com/petermolnar/nasg',
    license=open('./LICENSE').read(),
    include_package_data=True,
)
