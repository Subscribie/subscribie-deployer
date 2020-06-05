import os, errno, shutil, re
from urllib.request import urlopen
import subprocess
from flask import Flask, request, redirect, url_for
import git
import json
import sqlite3
import datetime
from base64 import b64encode, urlsafe_b64encode
import random
from pathlib import Path
from flask_migrate import upgrade
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from uuid import uuid4

app = Flask(__name__)

db = SQLAlchemy()
db.init_app(app)
Migrate(app, db)

# Load .env settings
curDir = os.path.dirname(os.path.realpath(__file__))
app.config.from_pyfile('/'.join([curDir, '.env']))

@app.route('/', methods=['GET', 'POST'])
@app.route('/deploy', methods=['GET', 'POST'])
def deploy():
    payload = json.loads(request.data)
    filename = re.sub(r'\W+', '', payload['company']['name'])
    webaddress = filename.lower() + '.' + app.config['SUBSCRIBIE_DOMAIN']
    # Create directory for site
    try:
        dstDir = app.config['SITES_DIRECTORY'] + webaddress + '/'
        if Path(dstDir).exists():
            print("Site {} already exists. Exiting...".format(webaddress))
            exit()
        os.mkdir(dstDir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
        # Clone subscribie repo & set-up .env files
    try:
        git.Git(dstDir).clone("https://github.com/Subscribie/subscribie")
        repo = git.Repo(dstDir + 'subscribie')
        repo.git.checkout('167-remove-jamla-yaml-based-config')
        # Generate config.py file
        response = urlopen('https://raw.githubusercontent.com/Subscribie/subscribie/master/subscribie/config.py.example')
        configfile = response.read()
        with open(dstDir + 'subscribie' + '/instance/config.py', 'wb') as fh:
            fh.write(configfile)

    except Exception as e:
        print("Did not clone subscribie for some reason")
        print(e.message, e.args)
        pass
    # Clone Subscriber Matching Service
    try:
        git.Git(dstDir).clone('https://github.com/Subscribie/subscription-management-software')
    except Exception as e:
        print("Didn't clone subscriber matching service")
        print(e.message, e.args)
    # Create virtualenv & install subscribie requirements to it
    print("Creating virtualenv")
    call = subprocess.call('export LC_ALL=C.UTF-8; export LANG=C.UTF-8; virtualenv -p python3 venv', cwd= ''.join([dstDir, 'subscribie']), shell=True)
    # Activate virtualenv and install requirements
    call = subprocess.call('export LC_ALL=C.UTF-8; export LANG=C.UTF-8; . venv/bin/activate;pip install -r requirements.txt', cwd= ''.join([dstDir, 'subscribie']), shell=True)

    # Migrate the database
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + dstDir + 'data.db'
    upgrade(directory=dstDir + 'subscribie/migrations')

    # Seed users table with site owners email address so they can login
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()
    email = payload['users'][0]
    now = datetime.datetime.now()
    login_token = urlsafe_b64encode(os.urandom(24)).decode("utf-8")
    cur.execute("INSERT INTO user (email, created_at, active, login_token) VALUES (?,?,?,?)", (email, now, 1, login_token,))
    cur.execute("INSERT INTO payment_provider (gocardless_active, stripe_active) VALUES(0,0)")
    cur.execute("INSERT INTO module (name, src) VALUES ('module_seo_page_title', 'https://github.com/Subscribie/module-seo-page-title.git')")
    con.commit()                                                         
    con.close()

    # Seed company table
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()                                                   
    now = datetime.datetime.now()
    company_name = payload['company']['name']
    cur.execute("INSERT INTO company (created_at, name) VALUES (?,?)", (now, company_name)) 
    con.commit()                                                         
    con.close()

    # Seed the item table
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()                                                   
    now = datetime.datetime.now()
    title = payload['items'][0]['title']
    archived = 0
    uuid = str(uuid4())
    monthly_price = payload['items'][0]['monthly_price']
    sell_price = payload['items'][0]['sell_price']

    cur.execute("INSERT INTO item (created_at, archived, uuid, title, monthly_price, sell_price) VALUES (?,?,?,?,?,?)", (now, archived, uuid, title, monthly_price, sell_price))
    if monthly_price == 0:
        requires_subscription = 0
    else:
        requires_subscription = 1

    if sell_price == 0:
        requires_instant_payment = 0
    else:
        requires_instant_payment = 1
    
    # Item requirements
    cur.execute('''INSERT INTO item_requirements (id , created_at, item_id, 
                    instant_payment, subscription) 
                 VALUES ( 1, ?, 1, ?, ?)
                 ''', (now, requires_instant_payment, requires_subscription))
    # Item selling points
    con.commit()                                                         
    con.close()
    
    # Set JAMLA path, STATIC_FOLDER, and TEMPLATE_FOLDER
    jamlaPath = dstDir + 'jamla.yaml'
    cliWorkingDir = ''.join([dstDir, 'subscribie'])
    theme_folder = ''.join([dstDir, 'subscribie', '/themes/'])
    static_folder = ''.join([theme_folder, 'theme-jesmond/static/'])

    settings = ' '.join([
        '--JAMLA_PATH', jamlaPath,
        '--TEMPLATE_FOLDER', theme_folder,
        '--STATIC_FOLDER', static_folder, 
        '--UPLOADED_IMAGES_DEST', dstDir + 'static/',
        '--DB_FULL_PATH', dstDir + 'data.db',
        '--SUCCESS_REDIRECT_URL', 'https://' + webaddress + '/complete_mandate',
        '--THANKYOU_URL', 'https://' + webaddress + '/thankyou',
        '--MAIL_SERVER', app.config['MAIL_SERVER'],
        '--MAIL_PORT', "25",
        '--MAIL_DEFAULT_SENDER', app.config['EMAIL_LOGIN_FROM'],
        '--MAIL_USERNAME', app.config['MAIL_USERNAME'],
        '--MAIL_PASSWORD', ''.join(['"', app.config['MAIL_PASSWORD'], '"']),
        '--MAIL_USE_TLS' , app.config['MAIL_USE_TLS'],
        '--EMAIL_LOGIN_FROM', app.config['EMAIL_LOGIN_FROM'],
        '--GOCARDLESS_CLIENT_ID', app.config['DEPLOY_GOCARDLESS_CLIENT_ID'],
        '--GOCARDLESS_CLIENT_SECRET', app.config['DEPLOY_GOCARDLESS_CLIENT_SECRET'],
    ])
    subprocess.call('export LC_ALL=C.UTF-8; export LANG=C.UTF-8; subscribie setconfig ' + settings, cwd = cliWorkingDir\
                      , shell=True)

    with open(dstDir + 'subscribie/instance/config.py', 'a') as fp:
        modules_path = dstDir + 'subscribie/modules/'
        fp.write('MODULES_PATH="' + modules_path + '"' + "\n")
        fp.write('THEME_SRC="' + 'https://github.com/Subscribie/theme-jesmond.git' + '"' + "\n")
        fp.write('THEME_NAME="' + 'jesmond' + '"' + "\n")

    # Begin uwsgi vassal config creation
    # Open application skeleton (app.skel) file and append 
    # "subscribe-to = <website-hostname>" config entry for the new 
    # sites webaddress so that uwsgi's fastrouter can route the hostname.
    curDir = os.path.dirname(os.path.realpath(__file__))
    with open(curDir + '/' + 'app.skel') as f:
        contents = f.read()
        # Append uwsgi's subscribe-to line with hostname of new site:
        contents += "\nsubscribe-to = /tmp/sock2:" + webaddress + "\n"
        # Writeout <webaddress>.ini config to file. uwsgi watches for .ini files
        # uwsgi will automatically detect this .ini file and start
        # routing requests to the site
        with open(dstDir + '/' + webaddress + '.ini', 'w') as f:
            f.write(contents)

    login_url = ''.join(['https://', webaddress, '/auth/login/', login_token])

    return login_url

application = app
