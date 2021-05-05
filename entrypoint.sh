#!/bin/bash

LAMBDA_VIRTUALENV=/lambda-venv

if [ -f "${LAMBDA_REQUIREMENTS}" ]; then
    echo "Requirements file found at ${LAMBDA_REQUIREMENTS}, installing deps..."
    virtualenv ${LAMBDA_VIRTUALENV}
    export PYTHONUSERBASE=${LAMBDA_VIRTUALENV}
    ${LAMBDA_VIRTUALENV}/bin/pip3 install -r "${LAMBDA_REQUIREMENTS}"
else
    echo "LAMBDA_REQUIREMENTS not set skipping Lambda requirements installation"
fi

exec flask run ${@}
