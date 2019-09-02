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
      ${API_URL}/users -X POST \
      -d '{"name":"'${NAME}'", "cluster_name": "'${CLUSTER_NAME}'"}'
    if [[ $? -ne 0 ]]
    then
      info "Fail"
      die "Cannot create user: ${NAME}"
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
      echo -n $(echo $USER_TOKEN_PAYLOAD | grep -Po '(?<="access_token": ")[^"]+')
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
  make test
fi