"## flake8"
flake8 parliament/

"## pylint"
pylint --rcfile pylintrc parliament/

"## mypy"
mypy -p parliament

"## pyright"
pyright parliament/
