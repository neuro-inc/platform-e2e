IMAGE_NAME ?= platform-e2e
IMAGE_TAG ?= latest
CLUSTER_NAME ?= "default"
SOURCES = setup.py platform_e2e tests
TEST_OPTS = $(PYTEST_OPTS) --durations 10 --timeout 300 --verbose
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
	pip install -U pip setuptools
	pip install -e .[dev]
	pre-commit install

test:
	pytest $(TEST_OPTS) -m "$(TEST_MARKERS)" tests

test-verbose:
	pytest $(TEST_OPTS) -m "$(TEST_MARKERS)" --log-cli-level=INFO tests

format:
ifdef CI_LINT_RUN
	pre-commit run --all-files --show-diff-on-failure
else
	pre-commit run --all-files
endif

lint: format
	mypy $(SOURCES)

docker-test:
	@$(DOCKER_CMD) test

docker-test-verbose:
	@$(DOCKER_CMD) test-verbose

docker-lint:
	@$(DOCKER_CMD) lint

cluster-test:
	./cluster-test.sh -c $(CLUSTER_NAME)
