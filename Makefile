SOURCES = setup.py platform_e2e tests

setup:
	pip install -r requirements.txt


test:
	pytest tests


format:
	black $(SOURCES)
	isort -rc $(SOURCES)

lint:
	flake8
	black --check $(SOURCES)
	isort --check -rc $(SOURCES)
	mypy $(SOURCES)
