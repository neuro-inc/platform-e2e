SOURCES = setup.py platform_e2e tests

setup:
	pip install -U pip
	pip install -r requirements.txt
	pip install -U -e git+git@github.com:neuromation/platform-client-python.git@master#egg=neuromation
	pip install -e .
	pip list|grep neuromation

test:
	pytest --durations 10 --timeout 300 --verbose tests


test-verbose:
	pytest --durations 10 --timeout 300 --verbose --log-cli-level=INFO tests


format:
	black $(SOURCES)
	isort -rc $(SOURCES)

lint:
	flake8
	black --check $(SOURCES)
	isort --check -rc $(SOURCES)
	mypy $(SOURCES)
