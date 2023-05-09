from setuptools import setup, find_packages
import versioneer

short_descr = ("Tools for parsing, manipulating, and replaying QIIME 2 "
               "analyses leveraging the framework's decentralized provenance "
               "data tracking.")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='provenance_lib',
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=short_descr,
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/qiime2/provenance_lib',
    author='Chris Keefe',
    author_email='crk239@nau.edu',
    license='BSD-3-clause',
    scripts=['scripts/tab-replay', 'scripts/always-tab-complete.py'],
    packages=find_packages(),
    package_data={'': ['assets/*.txt', '*.bib']},
    python_requires='>=3.8',
    install_requires=['bibtexparser>=1.0', 'Click', 'flake8', 'mypy',
                      'networkx', 'pandas', 'pyyaml>=5.3', 'types-setuptools',
                      ],
    extras_require={
         'dev': ['pytest>=6', 'pytest-cov>=2.0'],
     },
    entry_points={
        'console_scripts': [
            'replay = provenance_lib.click_commands:replay'
             ]
    }
)
