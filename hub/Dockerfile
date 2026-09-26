FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY hub ./hub
RUN pip install --no-cache-dir .
ENV HUB_CONFIG=/config/config.yaml HUB_PORT=8000
VOLUME ["/config", "/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["home-alert-hub"]
