# platform-e2e

End-to-end tests for the platform.

### Run tests

```bash
make cluster-test
```

## Cluster under test variable

- CLUSTER_NAME

## Platform URI variables

- CLIENT_TEST_E2E_AUTH_URI, default `https://api.dev.apolo.us`
- CLIENT_TEST_E2E_ADMIN_URI, default `https://api.dev.apolo.us`
- CLIENT_TEST_E2E_API_URI, default `https://api.dev.apolo.us`

## Existing user token variables

- CLIENT_TEST_E2E_USER_TOKEN - jwt token of main user
- CLIENT_TEST_E2E_USER_TOKEN_ALT - jwt token of secondary user

## Admin token variable

- CLIENT_TEST_E2E_ADMIN_TOKEN - admin token with `USERS_MANAGE` permission

In this mode script will check if `neuro-{sha1(CLUSTER_NAME)[0:16]}-{1,2}` users exist. If not then script will create these users and then use their tokens for tests.

### Run tests inside docker

Image name: `platform-e2e`
How to run:

```bash
docker run --rm -t \
    -e CLIENT_TEST_E2E_USER_TOKEN \
    -e CLIENT_TEST_E2E_USER_TOKEN_ALT \
    -e CLIENT_TEST_E2E_ADMIN_TOKEN \
    -e CLUSTER_NAME \
    platform-e2e \
    cluster-test
```
