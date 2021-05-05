################################################################################
### Builder Image
################################################################################

FROM python:3.7-stretch AS builder

ENV PYTHON_VERSION 3.7
ENV PYTHONUSERBASE /venv
ENV PYTHONPATH /venv-dev/lib/python${PYTHON_VERSION}/site-packages:/venv/lib/python${PYTHON_VERSION}}/site-packages
ENV PATH $PATH:/venv-dev/bin:/venv/bin
ENV CRYPTOGRAPHY_DONT_BUILD_RUST 1

# Copy files needed to install app requirements
COPY ./*requirements.txt /src/

# Install app requirements in virtualenv
RUN mkdir /venv \
  && pip3 install --ignore-installed --user -U pyopenssl cryptography certifi idna ndg-httpsclient pyasn1 singledispatch virtualenv \
  && pip3 install --user -r /src/requirements.txt

# Copy the source code into the container
COPY . /src

################################################################################
### Production Image
################################################################################

FROM python:3.7-slim-stretch AS runtime

ENV TZ=America/Los_Angeles
ENV PYTHON_VERSION 3.7
ENV PYTHONPATH /:/lambda-venv/lib/python${PYTHON_VERSION}/site-packages:/venv/lib/python${PYTHON_VERSION}/site-packages
ENV PYTHONUNBUFFERED=1
ENV PATH $PATH:/venv/bin

ENV AWS_DEFAULT_REGION=us-east-1

ENV FLASK_APP=invoker
ENV FLASK_ENV=prod

ENV PACKAGE="git dumb-init"

RUN apt-get update \
  && apt-get install -y \
  ${PACKAGE} \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Copy the app and its dependencies
COPY --from=builder /src/ /webapp
COPY --from=builder /venv /venv

COPY entrypoint.sh /entrypoint.sh

WORKDIR /webapp

VOLUME /lambda-venv

EXPOSE 5000

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/entrypoint.sh"]
