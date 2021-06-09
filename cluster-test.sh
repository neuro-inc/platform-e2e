#!/usr/bin/env bash


die() {
    local MESSAGE=${1:-Unknown error}
    echo >&2
    echo "*** Error ***" >&2
    echo ${MESSAGE} >&2
    exit 1
}

info() {
      echo $@ >&2
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

    info -n "Creating user: ${NAME} ..."
    curl -sS --fail \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "${ADMIN_API_URL}/users" -X POST \
      -d '{"name":"'${NAME}'", "email": "'${NAME}@neu.ro'"}'
    if [[ $? -ne 0 ]]
    then
      info "Fail"
      die "Cannot create user: ${NAME}"
    fi

    info "Ok"
}

add_user_to_cluster() {
    local NAME=$1
    local ADMIN_TOKEN=$2

    mkdir -p "/tmp/neu.ro"
    RESPONSE_FILE="$(mktemp "/tmp/neu.ro/response.XXXXXX")"
    info -n "Assign cluster ${CLUSTER_NAME} to user: ${NAME} ..."
    HTTP_CODE="$(curl -s \
      -o "$RESPONSE_FILE" \
      -w "%{http_code}" \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "${ADMIN_API_URL}/clusters/${CLUSTER_NAME}/users" -X POST \
      -d '{"user_name":"'${NAME}'", "role": "user"}' \
    )"

    if [ "$HTTP_CODE" -ge "400" ]; then
        RESPONSE="$(cat "$RESPONSE_FILE")"
        if [ "$HTTP_CODE" != "400" ] || [[ "$RESPONSE" != *"already exists"* ]]; then
            info "Fail"
            die "Cannot assign cluster ${CLUSTER_NAME} to user: ${NAME}"
        fi
    fi
    info "Ok"
}


assign_blob_access() {
    local NAME=$1
    local ADMIN_TOKEN=$2

    mkdir -p "/tmp/neu.ro"
    RESPONSE_FILE="$(mktemp "/tmp/neu.ro/response.XXXXXX")"

    local BUCKET_NAME="neuro-test-e2e-${NAME}"
    info -n "Give access for user: ${NAME} to bucket: ${BUCKET_NAME} ..."
    HTTP_CODE="$(curl -s \
      -o "$RESPONSE_FILE" \
      -w "%{http_code}" \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "${API_URL}/users/${USER_NAME}/permissions" -X POST \
      -d "[{\"uri\": \"blob://${CLUSTER_NAME}\", \"action\": \"write\"}]" \
    )"
    if [ "$HTTP_CODE" -ge "400" ]; then
        RESPONSE="$(cat "$RESPONSE_FILE")"
        if [ "$HTTP_CODE" != "400" ]; then
            info "Fail"
            die "Cannot give access for bucket ${BUCKET_NAME} to user: ${NAME}"
        fi
    fi

    info "Ok"
}

user_token() {
    local NAME=$1
    local ADMIN_TOKEN=$2
    local FAIL=$3

    info -n "Fetching user token: ${NAME} ..."
    local USER_TOKEN_PAYLOAD=`curl -sS --fail \
      -H 'Accept: application/json' -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      ${API_URL}/users/${NAME}/token -X POST`
    if [ $? -ne 0 ]
    then
      info "Failed"
      if [ ! -z "$FAIL" ]
      then
        die "Cannot fetch user token: $NAME"
      fi
    else
      info "Ok"
      echo -n $(echo $USER_TOKEN_PAYLOAD | jq -r .access_token)
    fi
}

usage() {
    echo "Usage: cluster-test.sh OPTIONS"
    echo
    echo "Options:"
    echo "  -c CLUSTER_NAME name of cluster, optional"
    echo "  -d for runing tests inside docker image"
    exit 1
}


CLUSTER_NAME=default
RUN_MODE=native
API_URL=${CLIENT_TEST_E2E_URI:-https://dev.neu.ro/api/v1}
APIS_URL=${API_URL/\/api\/v1/\/apis}
ADMIN_API_URL=$APIS_URL/admin/v1

while getopts c:d OPTION; do
  case "$OPTION" in
    c)
      CLUSTER_NAME=$OPTARG
      ;;
    d)
      RUN_MODE=docker
      ;;
    ?)
      usage
      ;;
  esac
done

info "Cluster: $CLUSTER_NAME"

if [ -z "$CLIENT_TEST_E2E_USER_NAME" ]
then
    check_admin_token
    HASH=$(echo -n $CLUSTER_NAME | sha1sum)
    USER_NAME="neuro-${HASH:0:16}-1"
    CLIENT_TEST_E2E_USER_NAME=$(user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN)
    if [ -z "${CLIENT_TEST_E2E_USER_NAME}" ]
    then
        create_user $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
        CLIENT_TEST_E2E_USER_NAME=$(user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN true)
    fi
    add_user_to_cluster $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
    assign_blob_access $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
else
  info "Using existing CLIENT_TEST_E2E_USER_NAME"
fi

if [ -z "$CLIENT_TEST_E2E_USER_NAME_ALT" ]
then
    check_admin_token
    HASH=$(echo -n $CLUSTER_NAME | sha1sum)
    USER_NAME="neuro-${HASH:0:16}-2"
    CLIENT_TEST_E2E_USER_NAME_ALT=$(user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN)
    if [ -z "${CLIENT_TEST_E2E_USER_NAME_ALT}" ]
    then
        create_user $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
        CLIENT_TEST_E2E_USER_NAME=$(user_token $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN true)
    fi
    add_user_to_cluster $USER_NAME $CLIENT_TEST_E2E_ADMIN_TOKEN
else
  info "Using existing CLIENT_TEST_E2E_USER_NAME_ALT"
fi

export CLIENT_TEST_E2E_USER_NAME
export CLIENT_TEST_E2E_USER_NAME_ALT
export CLIENT_TEST_E2E_URL

if [ "$RUN_MODE" = "docker" ]
then
  info "Run tests in docker image"
  IMAGE_NAME=${IMAGE_NAME:-platform-e2e}
  IMAGE_TAG=${IMAGE_TAG:-latest}
  DOCKER_CMD="docker run -t -e CLIENT_TEST_E2E_USER_NAME -e CLIENT_TEST_E2E_USER_NAME_ALT -e CLIENT_TEST_E2E_URI ${IMAGE_NAME}:${IMAGE_TAG}"
  $DOCKER_CMD test
else
  info "Run tests"

  export PYTEST_RETRIES=${PYTEST_RETRIES:-1}
  export PYTEST_OPTS="$PYTEST_OPTS --exitfirst --stepwise"

  for ((i=1; i<=$PYTEST_RETRIES; i++))
  do
    make test
  done
fi
