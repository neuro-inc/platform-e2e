FROM fedora:33

LABEL org.opencontainers.image.source = "https://github.com/neuro-inc/platform-e2e"

RUN echo -e max_parallel_downloads=10\\nfastestmirror=true >> /etc/dnf/dnf.conf && \
    dnf install -y --exclude container-selinux podman-2.1.1-10.fc33 make && \
    rm -rf /var/cache /var/log/dnf* /var/log/yum.*

RUN rm -rf  /var/lib/containers/ && \
    sed -i -e 's/driver = "overlay"/driver = "vfs"/' -e 's/mountopt = /#mountopt = /' /etc/containers/storage.conf && \
    podman info && \
    ln -s /usr/bin/podman /usr/bin/docker

ENV BUILDAH_FORMAT=docker

# clusters created during CI process use letsencrypt staging environment
# install letsencrypt staging environment certificate to trust store
RUN curl -o /etc/pki/ca-trust/source/anchors/letsencrypt-stg-root-x1.pem https://letsencrypt.org/certs/staging/letsencrypt-stg-root-x1.pem \
    && update-ca-trust

WORKDIR /app

ENV PATH=/root/.local/bin:$PATH

RUN python3 -m ensurepip --upgrade
RUN python3 -m venv .venv
RUN . .venv/bin/activate && pip install -U pip

COPY setup.cfg setup.cfg
COPY pyproject.toml pyproject.toml

RUN . .venv/bin/activate && pip install .

COPY platform_e2e platform_e2e

RUN . .venv/bin/activate && pip install .

COPY tests tests
COPY scripts scripts
COPY Makefile Makefile

ENTRYPOINT ["/usr/bin/make"]
