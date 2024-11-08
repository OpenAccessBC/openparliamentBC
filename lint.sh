#!/bin/bash

flake8 parliament/
pylint --rcfile pylintrc parliament/
mypy parliament/
pyright parliament/
