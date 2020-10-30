IMAGE_NAME ?= platform-e2e
IMAGE_TAG ?= latest
CLUSTER_NAME ?= "default"
SOURCES = setup.py platform_e2e tests
TEST_OPTS = --durations 10 --timeout 300 --verbose
DOCKER_CMD := docker run -t -e CLIENT_TEST_E2E_USER_NAME -e CLIENT_TEST_E2E_USER_NAME_ALT -e CLIENT_TEST_E2E_URI $(IMAGE_NAME):$(IMAGE_TAG)

ifdef SKIP_NETWORK_ISOLATION_TEST
	TEST_MARKERS := not network_isolation $(TEST_MARKERS)
endif

ifdef SKIP_BLOB_STORAGE_TESTS
ifneq ($(TEST_MARKERS),)
	TEST_MARKERS := and $(TEST_MARKERS)
endif
	TEST_MARKERS := not blob_storage $(TEST_MARKERS)
endif

build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

setup:
	pip install -U pip
	pip install -r requirements.txt
	pip install -U -e git+https://github.com/neuromation/platform-client-python.git@master#egg=neuromation
	pip install -e .
	pip list|grep neuromation
	pre-commit install

test:
	pytest ${TEST_OPTS} -m "$(TEST_MARKERS)" tests

test-verbose:
	pytest ${TEST_OPTS} -m "$(TEST_MARKERS)" --log-cli-level=INFO tests

format:
	pre-commit run --all-files --show-diff-on-failure

lint: format
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
