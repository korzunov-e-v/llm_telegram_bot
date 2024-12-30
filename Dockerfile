FROM python:3.12

WORKDIR /srv

COPY requirements.txt /srv

RUN pip install -r requirements.txt

COPY src /srv/src

ENV PYTHONPATH=$PYTHONPATH:/srv:/srv/src
CMD python /srv/src/bot.py
