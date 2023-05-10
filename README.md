# OpenViSUS Visualization project

The official OpenVisus C++ GitHub repository is [here](https://github.com/sci-visus/OpenVisus).

# Install openvisuspy

Create a virtual environment. This step is optional, but best to avoid conflicts:

```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

Install python packages, technically only `numpy` is stricly needed, but to access cloud storage and show dashboards/notebooks, you need additional packages too.

```
python3 -m pip install numpy boto3 xmltodict colorcet requests scikit-image matplotlib bokeh panel itkwidgets[all] pyvista vtk jupyter
```

Next, nstall Openvisus packages. 

If you **do not need the OpenVisus viewer** (or if you are in Windows WSL):

```
python3 -m pip install --upgrade OpenVisusNoGui
python3 -m pip install --upgrade openvisuspy 
```

if **you do need the OpenVisus viewer**:

```
python3 -m pip install --upgrade OpenVisus
python3 -m OpenVisus configure 
python3 -m pip install --upgrade openvisuspy 
```

# Examples

## Bokeh Dashboards 

```
python3 -m bokeh serve "examples/dashboards/run.py"  --dev --address localhost --args --single
python3 -m bokeh serve "examples/dashboards/run.py"  --dev --address localhost --args --multi
python3 -m bokeh serve "examples/dashboards/nasa.py" --dev --address localhost --args --single
```

Other misc examples:

```
python -m bokeh serve "examples/dashboards/run.py"  --dev --args --dataset  "https://atlantis.sci.utah.edu/mod_visus?dataset=david_subsampled&cached=1" --palette Greys256    --palette-range "[0, 255]"
python -m bokeh serve "examples/dashboards/run.py"  --dev --args --dataset  "https://atlantis.sci.utah.edu/mod_visus?dataset=2kbit1&cached=1"           --palette Greys256    --palette-range "[0, 255]"
python -m bokeh serve "examples/dashboards/run.py"  --dev --args --dataset  "https://atlantis.sci.utah.edu/mod_visus?dataset=chess-zip&cached=1"        --palette Viridis256  --palette-range "[-0.017141795, 0.012004322]" --num-views 3 

```

## Panel Dashboards 

```
python -m panel serve "examples/dashboards/run.py"  --dev --address localhost --args --single
python -m panel serve "examples/dashboards/run.py"  --dev --address localhost --args --multi
python -m panel serve "examples/dashboards/nasa.py" --dev --address localhost --args --single
```

## Jupyter Notebooks 

```
python3 -m jupyter notebook ./examples/notebooks 
```
