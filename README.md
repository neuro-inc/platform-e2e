# platform-e2e


End-to-end tests for the platform.

## ENV variables

* CLIENT_TEST_E2E_USER_NAME
* CLIENT_TEST_E2E_USER_NAME_ALT
* CLIENT_TEST_E2E_URI

## Docker image

Image name: `platform-e2e`
How to run:
```bash
    docker run -t -e CLIENT_TEST_E2E_USER_NAME -e CLIENT_TEST_E2E_USER_NAME_ALT -e CLIENT_TEST_E2E_URI make test

```
