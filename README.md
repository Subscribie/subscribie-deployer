# Subscribie Deployer 

Standalone flask app which receives a new site build request, and builds
the site. (ref https://github.com/Subscribie/module-builder/issues/7)

Responsible for building new subscribie sites.

- When a new site is created (via /start-building), all
  data needed to build the site is sent (as json) to this endpoint which then builds
  a new subscribie site
- Site settings are in an .env file
- Each site runes in its own isolates process (using uwisgi), using the same subscribie repo
  - Note Each site runs independently with its own database, but the codebase is *not* duplicated.
  - This is different from a previous implementation which cloned the Subscribie repo for each
    new site.
- Each site runs as a uwsgi 'vassal' which allows new sites to come online
  without having to restart the web server

## Configuration

#### Create virtual env & install requirements: 

`virtualenv -p python3 venv`
`. venv/bin/activate`
`pip install -r requirements.txt`

- Copy .env.example to .env
  - Edit SITES_DIRECTORY to directory where to deploy sites to
  - And all other env settings

For running locally in development: `./run.sh`

### Speed improvements

- Clone subscribie to a folder on a deployment server. Set `SUBSCRIBIE_REPO_DIRECTORY` to the repo folder.

- Create a `virtualenv` folder and set to `PYTHON_VENV_DIRECTORY`, pip install the requirements.txt
- Go into the subscribie shared repo, and create a database schema using `flask db upgrade` inside `PYTHON_VENV_DIRECTORY`
  - Copy `.env.example` to `.env` and set `SQLALCHEMY_DATABASE_URI` to `SUBSCRIBIE_REPO_DIRECTORY` root (the empty schema is copied to new sites to speed up new site deployments
- Back into this repo (deployer) Set `PYTHON_PATH_INJECT` to the same value as `SUBSCRIBIE_REPO_DIRECTORY`


## mod_wsgi Notes & Example apache2 config

[`mod_wsgi`](https://modwsgi.readthedocs.io/en/master/) is bound to the host python version,
so they must be in sync (this is different from uwsgi).

The python version for `mod_wsgi` must therefore be the same as the virtual environment compiled in the apache
module.

```
<VirtualHost *:80>
  
    ServerName api.example.co.uk
    DocumentRoot /home/<user>/www/api.example.co.uk


    RewriteEngine On

    WSGIScriptAlias / /home/<user>/www/api.example.co.uk/main.py
    WSGIDaemonProcess api eviction-timeout=30 graceful-timeout=30 header-buffer-size=327680 user=<user> group=<user> processes=1 threads=1 python-home=/home/<user>/www/api.example.co.uk/venv python-path=/home/<user>/www/api.example.co.uk/ display-name=api
    WSGIProcessGroup api
    LogLevel Debug
    ErrorLog /var/log/apache2/api.example.co.uk.error.log
    LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-agent}i\"" combined
    CustomLog /var/log/apache2/api.example.co.uk.access.log combined


    <Directory "/home/<user>/www/api.example.co.uk">
        Order allow,deny
        Allow from all
        Require all granted
    </Directory>

</VirtualHost>
```


### UWSGI notes
How to run: 

uwsgi --ini config.ini # add -d to demonize

Ensure that dir /tmp/sockets/ exists (for the vassal sites .ini 
  files)

Then chmod <number> /tmp/sock1 (todo fix this using chmod uwsgi flag)


## Example Nginx Config (deployer)

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
## Apache config example (deployer)

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
