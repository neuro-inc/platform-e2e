IMAGE_NAME ?= platform-e2e
IMAGE_TAG ?= latest
IMAGE ?= $(GKE_DOCKER_REGISTRY)/$(GKE_PROJECT_ID)/$(IMAGE_NAME)
CLUSTER_NAME ?= "default"
SOURCES = setup.py platform_e2e tests
TEST_OPTS = --durations 10 --timeout 300 --verbose
DOCKER_CMD := docker run -t -e CLIENT_TEST_E2E_USER_NAME -e CLIENT_TEST_E2E_USER_NAME_ALT -e CLIENT_TEST_E2E_URI $(IMAGE_NAME):$(IMAGE_TAG)

SKIP_NETWORK_ISOLATION_TEST_FLAG ?= $(SKIP_NETWORK_ISOLATION_TEST)
ifneq ($(SKIP_NETWORK_ISOLATION_TEST_FLAG),)
	TEST_OPTS := ${TEST_OPTS} -m "not network_isolation"
endif

build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

setup:
	pip install -U pip
	pip install -r requirements.txt
	pip install -U -e git+git@github.com:neuromation/platform-client-python.git@master#egg=neuromation
	pip install -e .
	pip list|grep neuromation

test:
	pytest ${TEST_OPTS} tests

test-verbose:
	pytest ${TEST_OPTS} --log-cli-level=INFO tests

format:
	black $(SOURCES)
	isort -rc $(SOURCES)

lint:
	flake8 $(SOURCES)
	black --check $(SOURCES)
	isort --check -rc $(SOURCES)
	mypy $(SOURCES)

_docker-setup:
	pip install -e .

docker-test:
	@$(DOCKER_CMD) test

docker-test-verbose:
	@$(DOCKER_CMD) test-verbose

docker-lint:
	@$(DOCKER_CMD) lint

cluster-test:
	./cluster-test.sh -c $(CLUSTER_NAME)
