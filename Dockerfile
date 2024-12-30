FROM python:3.12

WORKDIR /srv

COPY src /srv/src
COPY requirements.txt /srv

RUN pip install -r requirements.txt

ENV PYTHONPATH=$PYTHONPATH:/srv:/srv/src

CMD python /srv/src/bot.py
