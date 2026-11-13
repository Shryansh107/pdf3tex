FROM scratch
COPY tectonic /tectonic
COPY cache/tectonic /cache/tectonic
ENV XDG_CACHE_HOME=/cache HOME=/tmp
WORKDIR /work
ENTRYPOINT ["/tectonic"]
