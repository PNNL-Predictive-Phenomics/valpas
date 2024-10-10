# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'VaLPAS'
copyright = '2024, Yannick Mahlich, Logan Lewis, Jason McDermott'
author = 'Yannick Mahlich, Logan Lewis, Jason McDermott'
release = '0.1'

# -- Pathsetup ------
import os
import sys
sys.path.insert(0, os.path.abspath('../../src/'))
# sys.path.insert(0, os.path.abspath('../../src/valpas'))


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    # 'sphinx.ext.viewcode',
    'sphinx.ext.autosummary',
    # 'autoapi.extension'
]
# autoapi_dirs = ['../../src']
# autosummary_generate = True
templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_static_path = ['_static']


