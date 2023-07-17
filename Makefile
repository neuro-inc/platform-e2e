
TEST_OPTS = $(PYTEST_OPTS) --durations 10 --timeout 300 --verbose

ifdef SKIP_NETWORK_ISOLATION_TEST
	TEST_MARKERS := not network_isolation $(TEST_MARKERS)
endif

ifdef SKIP_BLOB_STORAGE_TESTS
ifneq ($(TEST_MARKERS),)
	TEST_MARKERS := and $(TEST_MARKERS)
endif
	TEST_MARKERS := not blob_storage $(TEST_MARKERS)
endif

.venv:
ifndef CI
	pyenv install --skip-existing
endif
	python -m venv .venv
	. .venv/bin/activate; \
	pip install -U pip

setup: .venv
	. .venv/bin/activate; \
	pip install -e .[dev]; \
	pre-commit install

test:
	. .venv/bin/activate; \
	pytest $(TEST_OPTS) -m "$(TEST_MARKERS)" tests

test-verbose:
	. .venv/bin/activate; \
	pytest $(TEST_OPTS) -m "$(TEST_MARKERS)" --log-cli-level=INFO tests

format:
ifdef CI_LINT_RUN
	. .venv/bin/activate; \
	pre-commit run --all-files --show-diff-on-failure
else
	. .venv/bin/activate; \
	pre-commit run --all-files
endif

lint: format
	. .venv/bin/activate; \
	mypy platform_e2e tests

docker-build:
	docker build -t platform-e2e:latest .

DOCKER_CMD := docker run -t --rm -e CLUSTER_NAME -e CLIENT_TEST_E2E_ADMIN_TOKEN -e CLIENT_TEST_E2E_USER_TOKEN -e CLIENT_TEST_E2E_USER_TOKEN_ALT -e CLIENT_TEST_E2E_AUTH_URI -e CLIENT_TEST_E2E_ADMIN_URI -e CLIENT_TEST_E2E_API_URI platform-e2e:latest

docker-test:
	@$(DOCKER_CMD) test

docker-test-verbose:
	@$(DOCKER_CMD) test-verbose

cluster-test:
	scripts/run_tests.sh
