SOURCES = setup.py platform_e2e tests

setup:
	pip install -r requirements.txt


test:
	pytest --durations 10 --timeout 300 --verbose tests


format:
	black $(SOURCES)
	isort -rc $(SOURCES)

lint:
	flake8
	black --check $(SOURCES)
	isort --check -rc $(SOURCES)
	mypy $(SOURCES)
