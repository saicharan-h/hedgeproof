# hedgeproof-sandbox: runs one generated estimator, one data window at a time.
# Network, filesystem, user and resource limits are applied by the runner's
# `docker run` flags (src/hedgeproof/sandbox.py), not by this image.
FROM python:3.12-slim
# Optional build-time CA (only for build hosts behind a TLS-inspecting proxy);
# mounted as a BuildKit secret, so it is never stored in the image.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir numpy==2.5.4
COPY harness.py /opt/hedgeproof/harness.py
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "/opt/hedgeproof/harness.py"]
