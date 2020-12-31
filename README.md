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

#### Create virtual env & install requirements: 

`virtualenv -p python3 venv`
`. venv/bin/activate`
`pip install -r requirements.txt`

- Copy .env.example to .env
  - Edit SITES_DIRECTORY to directory where to deploy sites to

For running locally in development: `./run.sh`

### Speed improvements

- Clone subscribie to a folder on a deployment server. Set `SUBSCRIBIE_REPO_DIRECTORY` to the repo folder.

- Create a `virtualenv` folder and set to `PYTHON_VENV_DIRECTORY`, pip install the requirements.txt
- Create a database schema using `flask db upgrade` inside `PYTHON_VENV_DIRECTORY`
  - Copy `.env.example` to `.env` and set `SQLALCHEMY_DATABASE_URI` to `SUBSCRIBIE_REPO_DIRECTORY` root (the empty schema is copied to new sites to speed up new site deployments
- Set `PYTHON_PATH_INJECT` to the same value as `SUBSCRIBIE_REPO_DIRECTORY`

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
