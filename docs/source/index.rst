.. VaLPAS documentation master file, created by
   sphinx-quickstart on Mon Oct  7 10:22:28 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

VaLPAS documentation
====================

VaLPAS identifies associations among molecular features measured across shared
experimental conditions. Begin with the :doc:`user_guide` for method selection,
input conventions, autoencoder configuration, and runnable workflows.

============
Installation
============

-----------------------
1. Clone the Repository
-----------------------

.. code-block:: sh

   git clone <repository-url>
   cd <repository-name>

-----------------------------
2. Create Virtual Environment
-----------------------------

Steps 2. & 3. are only necessary if an encapuslated virtual python environment is desired.
An alternative to `venv` is to use `conda`.
For more information on anaconda / conda refer to `https://anaconda.org/ <https://anaconda.org/>`__.
If no virtual environment is desired or already exists skip to Step 4.

.. code-block:: sh

   python -m venv valpas-env

-------------------------------
3. Activate Virtual Environment
-------------------------------

To activate the virtual environment use the appropirate command listed below.

.. code-block:: sh
   :caption: Windows

   valpas-env\Scripts\activate

.. code-block:: sh
   :caption: macOS/Linux

   source valpas-env/bin/activate

-------------------
4. Install `valpas`
-------------------

.. code-block:: sh
   
   pip install .


-------------------------------------------------------------
5. Install Additional Dependencies for Demonstration Notebook
-------------------------------------------------------------

These dependencies are only necessary if the included `demonstration notebook <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/notebooks/valpas_demonstration.ipynb>`__ is being run locally.

.. code-block:: sh
   
   pip install -r requirements.txt

=========================
Quick Setup (One Command)
=========================

.. code-block:: powershell
   :caption: Windows

   python -m venv valpas-env && valpas-env\Scripts\activate && pip install . && pip install -r requirements.txt


.. code-block:: sh
   :caption: macOS/Linux

   python -m venv valpas-env && source valpas-env/bin/activate && pip install . && pip install -r requirements.txt


=====
Usage
=====

------------------------
Starting the Environment
------------------------
Always activate the virtual environment before working on the project.

.. code-block:: powershell
   :caption: Windows

   valpas-env\Scripts\activate

.. code-block:: sh
   :caption: macOS/Linux

   source valpas-env/bin/activate

---------------
Running Jupyter
---------------

Once the environment is activated, start Jupyter:

.. code-block:: sh

   jupyter notebook

or

.. code-block:: sh

   jupyter lab

----------------------------
Deactivating the Environment
----------------------------

When you're done working:

.. code-block:: sh

   deactivate

============
Dependencies
============

The project uses the following main libraries:

* **Jupyter**: Interactive notebook environment
* **PyTorch**: Deep learning framework
* **Scikit-learn**: Machine learning library
* **Matplotlib**: Plotting library
* **Seaborn**: Statistical data visualization

===============
Troubleshooting
===============

---------------------
Python Version Issues
---------------------

If you need a specific Python version, create the environment with:

.. code-block:: sh
   
   python3.13 -m venv valpas-env  # Replace 3.13 with your desired version

-------------------
PyTorch GPU Support
-------------------

For CUDA-enabled PyTorch installation, visit  `pytorch.org <https://pytorch.org/get-started/locally/>`__ update `torch` with the appropriate command for your system.

.. code-block:: sh

   pip install --force-reinstall torch torchvision --index-url <specified url>

-----------------
Permission Issues
-----------------

If you encounter permission errors, try:

.. code-block:: sh

   pip install --user .
   pip install --user -r requirements.txt


==========
User guide
==========

.. toctree::
   :maxdepth: 1

   user_guide

=============
API Reference
=============

.. toctree::
   :maxdepth: 1

   api



