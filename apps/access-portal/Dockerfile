FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup -S portal && adduser -S -G portal -u 10001 portal
COPY app.py index.html app.js style.css ./
USER portal
EXPOSE 8083
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD wget -qO- http://127.0.0.1:8083/health >/dev/null || exit 1
CMD ["python", "app.py"]
