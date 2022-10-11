FROM python:3.10.7
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app
COPY . .
RUN pip install -r requirements.txt

#CMD ["python", "-m",  "http.server", "8000"]
CMD uvicorn --reload main:app --host 0.0.0.0 --port 5001
