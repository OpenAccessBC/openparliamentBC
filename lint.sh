#!/bin/bash

flake8 parliament/
pylint --rcfile pylintrc parliament/
mypy -p parliament
pyright parliament/
