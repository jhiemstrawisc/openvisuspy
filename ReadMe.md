# Instructions

See [https://github.com/sci-visus/OpenVisus]()

```
python -m pip install --upgrade openvisus_py
```

Run notebooks:

```
python -m jupyter notebook ./examples/notebooks
```

Run bokeh dashboard:

```
python -m bokeh serve "examples/python/bokeh-example.py"  --dev --log-level=debug --address localhost --port 8888 
```

# PyPi distribution

```
python3 setup.py sdist upload

```

# Internal debugging

example in Windows prompt:

```
set PYTHONPATH=C:\projects\OpenVisus\build\RelWithDebInfo;C:\projects\openvisus_py\src
set VISUS_BACKEND=cpp
```