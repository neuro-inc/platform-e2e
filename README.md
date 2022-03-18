# platform-e2e


End-to-end tests for the platform.


## cluster-test.sh

Run e2e tests inside docker image or on the host.

Usage:
```bash
Usage: cluster-test.sh OPTIONS

Options:
  -c CLUSTER_NAME name of cluster, optional
  -d for runing tests inside docker image
```
By default script will run tests in `native` mode. Configured python and make required.

For `docker` mode only docker  and latest `platform-e2e` image required.


### Optional ENV vars

* CLIENT_TEST_E2E_AUTH_URI, default `https://dev.neu.ro`
* CLIENT_TEST_E2E_ADMIN_URI, default `https://dev.neu.ro`
* CLIENT_TEST_E2E_API_URI, default `https://dev.neu.ro`

### Run Test with existing users mode

Next ENV variables required:
* CLIENT_TEST_E2E_USER_NAME - jwt token of main user
* CLIENT_TEST_E2E_USER_NAME_ALT - jwt token of secondary user


### Run test with admin token

* CLIENT_TEST_E2E_ADMIN_TOKEN - admin token with `USERS_MANAGE` permission

In this mode script will check if `neuro-{sha1(CLUSTER_NAME)[0:16]}-{1,2}` users exist. If not then script will create these users self and then use their tokens for tests.




## You can also run all inside docker

Image name: `platform-e2e`
How to run:
```bash
    docker run -t \
        -e CLIENT_TEST_E2E_USER_NAME \
        -e CLIENT_TEST_E2E_USER_NAME_ALT \
        -e CLIENT_TEST_E2E_AUTH_URI \
        -e CLIENT_TEST_E2E_ADMIN_URI \
        -e CLIENT_TEST_E2E_API_URI \
        -e CLUSTER_NAME \
        platform-e2e \
        cluster-test
    docker run -t \
        -e CLIENT_TEST_E2E_ADMIN_TOKEN \
        -e CLIENT_TEST_E2E_AUTH_URI \
        -e CLIENT_TEST_E2E_ADMIN_URI \
        -e CLIENT_TEST_E2E_API_URI \
        -e CLUSTER_NAME \
        platform-e2e \
        cluster-test

```
