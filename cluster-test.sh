#!/usr/bin/env bash

CLUSTER_NAME=$1
RUN_MODE=$2

API_URL=${CLIENT_TEST_E2E_URI:-https://dev.neu.ro/api/v1}
USER_TOKEN=""


die() {
    local MESSAGE=${1:-Unknown error} >&2
    echo >&2
    echo "*** Error ***" >&2
    echo ${MESSAGE} >&2
    exit -1
}

check_admin_token() {
  if [[ -z "$CLIENT_TEST_E2E_ADMIN_TOKEN" ]]
  then
    die "Admin token ENV variable empty: CLIENT_TEST_E2E_ADMIN_TOKEN"
  fi

}

create_user() {
    local NAME=$1
    local ADMIN_TOKEN=$2
    echo -n "Creating user: ${NAME} ..."
    curl -sS --fail \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      ${API_URL}/users -X POST \
      -d '{"name":"'${NAME}'", "cluster_name": "'${CLUSTER_NAME}'"}'
    if [[ $? -ne 0 ]]
    then
      echo "Fail"
      die "Cannot create user: ${NAME}"
    fi
    echo "Ok"
}

user_token() {
    local NAME=$1
    local ADMIN_TOKEN=$2
    local FAIL=$3
    echo  -n "Fetching user token: ${NAME} ..."
    USER_TOKEN_PAYLOAD=`curl -sS --fail \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      ${API_URL}/users/${NAME}/token -X POST`
    if [ $? -ne 0 ]
    then
      echo "Failed"
      if [ ! -z "$FAIL" ]
      then
        die "Cannot fetch user token: $NAME"
      fi
      USER_TOKEN=""
    else
      echo "Ok"
      USER_TOKEN=$(echo $USER_TOKEN_PAYLOAD | grep -Po '(?<="access_token": ")[^"]+')
    fi
}


if [ -z "$CLUSTER_NAME" ]
then
    echo "Usage: cluster-test.sh [CLUSTER_NAME|--default-cluster][ --docker]"
    echo "--default-cluster for neuromation cluster"
    echo "--docker for runing tests inside docker image"
    exit -1
fi

if [ "$CLUSTER_NAME" = "--default-cluster" ]
then
  CLUSTER_NAME="default-cluster"
fi


if [ -z "$CLIENT_TEST_E2E_USER_NAME" ]
then
    check_admin_token
    USER_NAME="neuromation-service-$CLUSTER_NAME"
    user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
    if [ -z "${USER_TOKEN}" ]
    then
        create_user $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
        user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN true
    fi
    CLIENT_TEST_E2E_USER_NAME="${USER_TOKEN}"
fi


if [ -z "$CLIENT_TEST_E2E_USER_NAME_ALT" ]
then
    check_admin_token
    USER_NAME="neuromation-test-$CLUSTER_NAME"
    user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
    if [ -z "${USER_TOKEN}" ]
    then
        create_user $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
        user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN true
    fi
    CLIENT_TEST_E2E_USER_NAME_ALT="${USER_TOKEN}"
fi

export CLIENT_TEST_E2E_USER_NAME
export CLIENT_TEST_E2E_USER_NAME_ALT
export CLIENT_TEST_E2E_URL
if [ "$RUN_MODE" = "--docker" ]
then
  IMAGE_NAME=${IMAGE_NAME:-platform-e2e}
  IMAGE_TAG=${IMAGE_TAG:-latest}
  DOCKER_CMD="docker run -t -e CLIENT_TEST_E2E_USER_NAME -e CLIENT_TEST_E2E_USER_NAME_ALT -e CLIENT_TEST_E2E_URI ${IMAGE_NAME}:${IMAGE_TAG}"
  $DOCKER_CMD test
else
  make test
fi