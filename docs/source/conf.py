# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

# -- Pathsetup ------
import os
import sys
sys.path.insert(0, os.path.abspath('../../src/'))
from valpas import __version__ as release_version


project = 'VaLPAS'
copyright = '2025 Battelle Memorial Institute'
author = 'Yannick Mahlich, Jason McDermott'
release = release_version



# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    # 'sphinx.ext.viewcode',
    'sphinx.ext.autosummary',
]
autosummary_generate = True
templates_path = ['_templates']
exclude_patterns = []

autodoc_mock_imports = [
    "bspline-mutual-information",
    "matplotlib",
    "matplotlib-venn",
    "networkx",
    "numpy",
    "openpyxl",
    "pandas",
    "plotly",
    "scikit-learn",
    "scipy",
    "seaborn",
    "torch",
    ]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_static_path = ['_static']

# Automatically extract typehints when specified and place them in
# descriptions of the relevant function/method.
autodoc_typehints = "description"

# Don't show class signature with the class' name.
autodoc_class_signature = "separated"
