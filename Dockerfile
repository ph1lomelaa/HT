FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app
COPY pligrim_bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app pligrim_bot /app/pligrim_bot
RUN mkdir -p /app/pligrim_bot/data/runtime && chown -R app:app /app/pligrim_bot/data/runtime
USER app
CMD ["python", "-m", "pligrim_bot.main"]
