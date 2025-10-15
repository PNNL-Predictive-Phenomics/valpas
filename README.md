## ValPAS

## Dependencies

### Creating the conda environment.
Valpas Environment Setup

This project requires Python and several data science libraries. Follow the instructions below to set up your development environment.

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

## Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Create Virtual Environment
```bash
python -m venv valpas-env
```

### 3. Activate Virtual Environment

**Windows:**
```bash
valpas-env\Scripts\activate
```

**macOS/Linux:**
```bash
source valpas-env/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Quick Setup (One Command)

**macOS/Linux:**
```bash
python -m venv valpas-env && source valpas-env/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv valpas-env && valpas-env\Scripts\activate && pip install --upgrade pip && pip install -r requirements.txt
```

## Usage

### Starting the Environment
Always activate the virtual environment before working on the project:

**Windows:**
```bash
valpas-env\Scripts\activate
```

**macOS/Linux:**
```bash
source valpas-env/bin/activate
```

### Running Jupyter
Once the environment is activated, start Jupyter:
```bash
jupyter notebook
```
or
```bash
jupyter lab
```

### Deactivating the Environment
When you're done working:
```bash
deactivate
```

## Dependencies

The project uses the following main libraries:
- **Jupyter**: Interactive notebook environment
- **PyTorch**: Deep learning framework
- **Scikit-learn**: Machine learning library
- **Matplotlib**: Plotting library
- **Seaborn**: Statistical data visualization

## Troubleshooting

### Python Version Issues
If you need a specific Python version, create the environment with:
```bash
python3.8 -m venv valpas-env  # Replace 3.8 with your desired version
```

### PyTorch GPU Support
For CUDA-enabled PyTorch installation, visit [pytorch.org](https://pytorch.org/get-started/locally/) and replace the `torch` line in `requirements.txt` with the appropriate command for your system.

### Permission Issues
If you encounter permission errors, try:
```bash
pip install --user -r requirements.txt
```

## Development

Remember to activate your virtual environment (`source valpas-env/bin/activate`) every time you work on this project.

## Running the notebook
### Within a browser
To start the jupyter server and initialize the notebook the conda environment has to be activated first. This can be done by invoking from within the root of the git-repository via:
```sh
conda activate valpas
```
Next the jupyter server has to be booted up. This is done via the command:
```sh
jupyter notebook
```
The command will also automatically open a browser window and redirect to `http://localhost:8888/` from where the actual jupyter notebook can be opened.

### Within VSCode
Running the notebook from within VSCode requires the installation of the [Jupyter extension]((https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter)). For more on VSCodes notebook functionality also see [here](https://code.visualstudio.com/docs/datascience/jupyter-notebooks). After opening the git repository as folder in VSCode and opening the jupyter notebook, the previously installed conda environment should be a selectable kernel option. If it is not available a restart of VSCode might help.
