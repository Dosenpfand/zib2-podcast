FROM python:3.11

WORKDIR /code

ENV TZ="Europe/Vienna"

RUN set -eux; \
	apt-get update; \
	apt-get install -y --no-install-recommends cron ffmpeg; \
	rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

ENV CRONTAB_FILE=/etc/cron.d/app_cron
COPY docker/crontab ${CRONTAB_FILE}
COPY docker/create_env.sh /code/create_env.sh
COPY docker/cron.sh /code/cron.sh

CMD ["uvicorn", "app.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
