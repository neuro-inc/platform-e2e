FROM fedora:31

LABEL org.opencontainers.image.source = "https://github.com/neuro-inc/platform-e2e"

#Based on https://developers.redhat.com/blog/2019/08/14/best-practices-for-running-buildah-in-a-container/

RUN echo -e max_parallel_downloads=10\\nfastestmirror=true >> /etc/dnf/dnf.conf && \
    dnf install -y --exclude container-selinux podman buildah python3 make gcc python3-devel jq && \
    rm -rf /var/cache /var/log/dnf* /var/log/yum.*

RUN rm -rf  /var/lib/containers/ && \
    sed -i -e 's/driver = "overlay"/driver = "vfs"/' -e 's/mountopt = /#mountopt = /' /etc/containers/storage.conf && \
    podman info && \
    ln -s /usr/bin/podman /usr/bin/docker


# clusters created during CI process use letsencrypt staging environment
# install letsencrypt staging environment certificate to trust store
RUN curl -o /etc/pki/ca-trust/source/anchors/fakelerootx1.pem https://letsencrypt.org/certs/fakelerootx1.pem \
    && update-ca-trust


RUN python3 -m venv /venv
ENV PATH=/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /platform-e2e

COPY setup.py setup.py

RUN pip install -U pip \
    && pip install -e . \
    && pip uninstall -y platform-e2e

COPY . /platform-e2e

RUN pip install -e .

ENV BUILDAH_FORMAT=docker

ENTRYPOINT ["/usr/bin/make"]
