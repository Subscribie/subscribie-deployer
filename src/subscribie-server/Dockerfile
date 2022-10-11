FROM httpd

WORKDIR /usr/src/app

COPY . .

RUN apt-get update && apt-get install -y python3 python3-pip

RUN pip install -r requirements.txt

# Enable httpd mod_proxy_uwsgi
RUN sed -i \
		-e 's/^#\(LoadModule .*mod_proxy_uwsgi.so\)/\1/' \
		conf/httpd.conf

