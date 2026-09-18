FROM langfuse/langfuse:4.38.0@sha256:47ef2f121e2959c8458c209d118949ade25778017e3f5b75b1e45f72276811c3
USER root
RUN apk add --no-cache python3 ca-certificates
COPY bootstrap.py patch_migrations.py /starter/
RUN python3 /starter/patch_migrations.py /app/packages/shared/clickhouse/scripts/up.sh
USER 1001:1001
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080 HOSTNAME=0.0.0.0
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/public/health', timeout=8)"
ENTRYPOINT ["dumb-init", "--", "python3", "/starter/bootstrap.py", "web"]
CMD []
