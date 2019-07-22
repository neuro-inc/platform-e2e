FROM python:3.7-slim

RUN apt-get -qy update && \
    apt-get -qy install build-essential && \
    apt-get -qy clean

COPY . /platform-e2e
WORKDIR /platform-e2e

RUN make _docker-setup

RUN apt-get -qy purge build-essential && \
    apt-get -qy autoremove --purge