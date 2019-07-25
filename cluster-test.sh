#!/usr/bin/env bash

CLUSTER_NAME=$1
API_URL=${CLIENT_TEST_E2E_URI:-https://dev.neu.ro/api/v1}
USER_TOKEN=""

die() {
    local MESSAGE=${1:-Unknown error}
    echo
    echo "*** Error ***"
    echo ${MESSAGE}
    exit -1
}

check_admin_token() {
  if [[ -z "$CLIENT_TEST_E2E_ADMIN_TOKEN" ]]
  then
    die "Admin token empty: CLIENT_TEST_E2E_ADMIN_TOKEN"
  fi

}

create_user() {
    local NAME=$1
    local ADMIN_TOKEN=$2
    echo -n "Creating user: ${NAME} ..."
    curl -s  --fail \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      ${API_URL}/users/${NAME} -X PUT \
      -d '{"name":"${NAME}", "cluster_name": "${CLUSTER_NAME}"}'
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
    USER_TOKEN=`curl -s --fail \
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
    fi
}


if [ -z "$CLUSTER_NAME" ]
then
    echo "Usage: cluster-test.sh CLUSTER_NAME"
    exit -1
fi


if [ -z "$CLIENT_TEST_E2E_USER_NAME" ]
then
    check_admin_token
    USER_NAME="neuromation_service_$CLUSTER_NAME"
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
    USER_NAME="neuromation_test_$CLUSTER_NAME"
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

make test CLIENT_TEST_E2E_USER_NAME=${CLIENT_TEST_E2E_USER_NAME}


