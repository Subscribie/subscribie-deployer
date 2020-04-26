# Subscribie Deployer 

Standalone flask app which receives a new site build request, and builds 
the site. (ref https://github.com/Subscribie/module-builder/issues/7)

Responsible for building new subscribie sites.

- When a new site is created (via /start-building) , all the
  data to build that site (in yaml) is sent to this endpoint which builds 
  a new subscribie site
- Each site is defined in a yaml file, and a clone of the Subscribie repo
- Each site runs as a uwsgi 'vassal' which allows new sites to come online
  without having to restart the web server

## Configuration

- Copy config.py.example to config.py
- Remove COUCHDB settings if not using it
- Set JAMLA_DEPLOY_URL to this app 


### UWSGI notes
How to run: 

uwsgi --ini config.ini # add -d to demonize

Ensure that dir /tmp/sockets/ exists (for the vassal sites .ini 
  files)

Then chmod <number> /tmp/sock1 (todo fix this using chmod uwsgi flag)


## Example Nginx Config

```
# mysite_nginx.conf
#

# configuration of the server
server {
    # the port your site will be served on
    listen      80;
    # the domain name it will serve for
    server_name *.app1 example.com ~^.*.example.com app2 site1.local site2.local; # substitute your machine's IP address or FQDN
    root /home/chris/Documents/python/uwsgi/vassals/;
    charset     utf-8;

    client_max_body_size 75M;

    # max upload size

    location / {
        #include /etc/nginx/uwsgi_params;
        uwsgi_pass unix:///tmp/sock1;
    }
}
```
## Apache config example

(Using ip rather than sockets)

```
<VirtualHost *:80>

  ServerAdmin webmaster@localhost
  DocumentRoot /var/www/html

  ErrorLog ${APACHE_LOG_DIR}/error.log
  CustomLog ${APACHE_LOG_DIR}/access.log combined

  ServerName example.com
  ServerAlias *.example.com
  ProxyPass / uwsgi://127.0.0.1:8001/

</VirtualHost>
```
