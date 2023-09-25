from setuptools import setup, find_packages
import versioneer

short_descr = ("Tools for parsing, manipulating, and replaying QIIME 2 "
               "analyses leveraging the framework's decentralized provenance "
               "data tracking.")

setup(
    name='provenance-lib',
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=short_descr,
    long_description=short_descr,
    long_description_content_type='text/markdown',
    url='https://github.com/qiime2/provenance-lib',
    author='Chris Keefe',
    author_email='crk239@nau.edu',
    license='BSD-3-Clause',
    scripts=['scripts/tab-replay', 'scripts/always-tab-complete.py'],
    packages=find_packages(),
    package_data={
        'provenance_lib': ['assets/*.txt', '*.bib'],
        'provenance_lib.tests': [
            'data/*',
            'data/lump_three_vars_test/*',
            'data/multiple_imports_test/*',
            'data/multiple_imports_test/duplicated_inner/*',
            'data/parse_dir_test/*',
            'data/parse_dir_test/inner/*'
        ]
    },
    python_requires='>=3.8',
    extras_require={
         'dev': ['pytest>=6', 'pytest-cov>=2.0'],
     },
    entry_points={
        'console_scripts': [
            'replay = provenance_lib.click_commands:replay'
             ]
    }
)
