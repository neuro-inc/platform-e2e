setup:
	pip install -r requirements.txt


test:
	pytest tests


format:
	black .
	isort -rc .

lint:
	flake8
	black --check .
	isort --check -rc .
	mypy .
