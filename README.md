# ValPAS prototype

## Dependencies

We recommend setting up a conda environment to handle dependencies. See [https://docs.conda.io/en/latest/](https://docs.conda.io/en/latest/) or [https://github.com/conda-forge/miniforge](https://github.com/conda-forge/miniforge) for more information on how to setup conda. Once conda is installed a conda environment containing all the required dependencies can be automatically setup by invoking the following command from the root folder of this repository.
```
conda create --name valpas-prototype --file requirements.txt
```
This will cerate a conda environment with the name `valpas-prototype` satisfying the required dependencies. 

## Running the notebook
### Within a browser
To start the jupyter server and initiailize the notebook the conda environment has to be activated first. This can be done by invoking from within the root of the git-repository via:
```
conda activate valpas-prototype
```
Next the jupyter server has to be booted up. This is done via the command:
```
jupyter notebook
```
The command will also automatically open a browser window and redirect to `http://localhost:8888/` from where the actual jupyter notebook can be opened.

### Within VSCode
Running the notebook from within VSCode requires the installation of the [Jupyter extension]((https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter)). For more on VSCodes notebook functionality also see [here](https://code.visualstudio.com/docs/datascience/jupyter-notebooks). After opening the git repository as folder in VSCode and opening the jupyter notebook, the previously installed conda environment should be a selectable kernel option. If it is not available a restart of VSCode might help.