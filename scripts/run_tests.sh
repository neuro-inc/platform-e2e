#!/usr/bin/env bash

export PYTEST_OPTS="$PYTEST_OPTS --exitfirst --stepwise"

RETRIES=${CLIENT_TEST_E2E_RETRIES:-1}

for ((i=0; i<=$RETRIES; i++))
do
    make test

    if [ $? == 0 ]
    then
        exit 0
    fi
done

exit 1
