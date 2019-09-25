FROM fedora:30

#Based on https://developers.redhat.com/blog/2019/08/14/best-practices-for-running-buildah-in-a-container/

RUN echo max_parallel_downloads=10\nfastestmirror=true>> /etc/dnf/dnf.conf && \
    yum install -y --exclude container-selinux podman buildah python3 make gcc python3-devel && \
    rm -rf /var/cache /var/log/dnf* /var/log/yum.*

RUN rm -rf  /var/lib/containers/ && \
    sed -i -e 's/driver = "overlay"/driver = "vfs"/' -e 's/mountopt = /#mountopt = /' /etc/containers/storage.conf && \
    podman info && \
    ln -s /usr/bin/podman /usr/bin/docker


RUN python3 -m venv /venv
ENV PATH=/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY . /platform-e2e
WORKDIR /platform-e2e

RUN make _docker-setup

ENTRYPOINT ["/usr/bin/make"]
