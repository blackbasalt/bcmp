FROM python:3.12-alpine
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /bcmp
COPY . /bcmp/
RUN pip install -r requirements.txt
