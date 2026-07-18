# Mako Reactor

## Development Install 

Make sure you have mamba-forge installed. This is basically anaconda with mamba installed by default which allows for faster installed. If you already have mamba/conda installed, you can skip this. 

Linux Users:
```bash
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh
bash Mambaforge-Linux-x86_64.sh -b -p ~/mambaforge3
Copy
```

Macintosh Users with Intel processors:

```bash
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-MacOSX-x86_64.sh
bash Mambaforge-MacOSX-x86_64.sh -b -p ~/mambaforge3
Copy
```

Macintosh Users with Apple Silicon processors:

```bash
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-MacOSX-arm64.sh
bash Mambaforge-MacOSX-arm64.sh -b -p ~/mambaforge3
```

Install dependencies and a development install of the library 

```bash
# install dependencies from environment file
# replace mamba with conda if you do not have mamba installed
mamba env create -f environment.yml -n mako

# activate new env
mamba activate mako

# install library 
python setup.py develop
```


