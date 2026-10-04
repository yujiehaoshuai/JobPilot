# 使用 Python 3.12；镜像只包含源代码与虚构 fixtures，不复制本机环境。
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright BROWSER_CHANNEL=chromium BROWSER_HEADLESS=true
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt && python -m playwright install --with-deps chromium
RUN useradd --create-home --uid 10001 jobpilot && mkdir -p /app/data /app/profiles && chown -R jobpilot:jobpilot /app /opt/playwright
COPY --chown=jobpilot:jobpilot app ./app
COPY --chown=jobpilot:jobpilot fixtures ./fixtures
COPY --chown=jobpilot:jobpilot migrations ./migrations
COPY --chown=jobpilot:jobpilot scripts ./scripts
COPY --chown=jobpilot:jobpilot alembic.ini pyproject.toml ./
USER jobpilot
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
