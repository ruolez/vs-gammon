FROM debian:trixie-slim

LABEL app=vs-gammon

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends gnubg python3 python3-flask python3-pil gunicorn ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/gnubg \
 && if [ ! -s /var/lib/gnubg/gnubg_ts0.bd ]; then /usr/games/makebearoff -t 6x6 -f /var/lib/gnubg/gnubg_ts0.bd; fi

WORKDIR /srv
COPY app /srv/app
COPY tests /srv/tests

EXPOSE 5563
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "300", "--bind", "0.0.0.0:5563", "app.main:create_app()"]
