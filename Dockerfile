FROM python:3.12

WORKDIR /srv

COPY src /srv/src
COPY requirements.txt /srv

RUN pip install requirements.txt

CMD python /srv/src/main.py
