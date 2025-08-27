# ValPAS prototype

## Dependencies

### Creating the conda environment.
We recommend setting up a conda environment. See [https://docs.conda.io/en/latest/](https://docs.conda.io/en/latest/) or [https://github.com/conda-forge/miniforge](https://github.com/conda-forge/miniforge) for more information on how to setup conda. Once conda is installed a conda environment containing all the base dependencies (`python` & `jupyter`) can be automatically setup by invoking the following command from the root folder of this repository.
```sh
conda env create --file environment.yml
```
This will cerate a conda environment with the name `valpas-prototype`. In case conda returns a `CondaValueError: prefix already exists: [...]` error, this is most likely due to the fact that the environment `valpas-prototype` already exsits. Either delete the environment via `conda env remove -n valpas-prototype` and reinstall or define a different environment name during setup (this can be done with the `-n` flag).

### Installing the valpas package
After checking out the git repository via `git clone git@github.com:PNNL-Predictive-Phenomics/valpas.git` navigate to the root folder of the repository. Make sure that the previously installed conda environment is active. This can be achieved via:
```sh
conda activate valpas
```
Once the environment is active run pip to install the valpas package from the local git copy.
```sh
pip install -e .
```
This will install the python package in "editable" mode, i.e. if changes to the package code are made, the package will not have to be reinstalled for those changes to go into effect.

## Running the notebook
### Within a browser
To start the jupyter server and initiailize the notebook the conda environment has to be activated first. This can be done by invoking from within the root of the git-repository via:
```sh
conda activate valpas-prototype
```
Next the jupyter server has to be booted up. This is done via the command:
```sh
jupyter notebook
```
The command will also automatically open a browser window and redirect to `http://localhost:8888/` from where the actual jupyter notebook can be opened.

### Within VSCode
Running the notebook from within VSCode requires the installation of the [Jupyter extension]((https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter)). For more on VSCodes notebook functionality also see [here](https://code.visualstudio.com/docs/datascience/jupyter-notebooks). After opening the git repository as folder in VSCode and opening the jupyter notebook, the previously installed conda environment should be a selectable kernel option. If it is not available a restart of VSCode might help.
