import os, errno, shutil, re
from urllib.request import urlopen
import subprocess
from flask import Flask, request, redirect, url_for
from werkzeug.security import generate_password_hash
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

        # Create .env file from .env.example
        envFileSrc = Path(dstDir + '/subscribie/.env.example')
        envFileDst = Path(dstDir + '/subscribie/.env')
        shutil.copy(envFileSrc, envFileDst)

        # Generate RSA keys for jwt auth
        subprocess.call(f'ssh-keygen -t rsa -N "" -f {dstDir}id_rsa', shell=True)

        # Update .env values for public & private keys
        privateKeyDst = dstDir + 'id_rsa'
        subprocess.call(f"dotenv -f {envFileDst} set PRIVATE_KEY {privateKeyDst}", shell=True)

        publicKeyDst = dstDir + 'id_rsa.pub'
        subprocess.call(f"dotenv -f {envFileDst} set PUBLIC_KEY {publicKeyDst}", shell=True)

        # Set SERVER_NAME in .env
        subprocess.call(f"dotenv -f {envFileDst} set SERVER_NAME {webaddress}", shell=True)

        # Set Stripe keys for Stripe connect
        subprocess.call(f"dotenv -f {envFileDst} set STRIPE_SECRET_KEY {app.config['STRIPE_SECRET_KEY']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set STRIPE_PUBLISHABLE_KEY {app.config['STRIPE_PUBLISHABLE_KEY']}", shell=True)

        # Update .env for stripe
        subprocess.call(f"dotenv -f {envFileDst} set STRIPE_SECRET_KEY {app.config['STRIPE_SECRET_KEY']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set STRIPE_PUBLISHABLE_KEY {app.config['STRIPE_PUBLISHABLE_KEY']}", shell=True)

        # Update .env values for mail
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_SERVER {app.config['MAIL_SERVER']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_PORT {app.config['MAIL_PORT']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_PORT {app.config['MAIL_PORT']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_USERNAME {app.config['MAIL_USERNAME']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_PASSWORD {app.config['MAIL_PASSWORD']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_DEFAULT_SENDER {app.config['EMAIL_LOGIN_FROM']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set MAIL_USE_TLS {app.config['MAIL_USE_TLS']}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set EMAIL_LOGIN_FROM {app.config['EMAIL_LOGIN_FROM']}", shell=True)

        uploadImgDst = dstDir + 'subscribie/static/'
        uploadedFilesDst = dstDir + 'subscribie/uploads/'
        subprocess.call(f"dotenv -f {envFileDst} set UPLOADED_IMAGES_DEST {uploadImgDst}", shell=True)
        subprocess.call(f"dotenv -f {envFileDst} set UPLOADED_FILES_DEST {uploadedFilesDst}", shell=True)

        successRedirectUrl = 'https://' + webaddress + '/complete_mandate'
        subprocess.call(f"dotenv -f {envFileDst} set SUCCESS_REDIRECT_URL {successRedirectUrl}", shell=True)

        thankyouUrl = 'https://' + webaddress + '/thankyou'
        subprocess.call(f"dotenv -f {envFileDst} set THANKYOU_URL {thankyouUrl}", shell=True)

    except Exception as e:
        print("Did not clone subscribie for some reason")
        print(e.message, e.args)
        pass

    # Create virtualenv & install subscribie requirements to it
    print("Creating virtualenv")
    call = subprocess.call('export LC_ALL=C.UTF-8; export LANG=C.UTF-8; virtualenv -p python3 venv', cwd= ''.join([dstDir, 'subscribie']), shell=True)
    # Activate virtualenv and install requirements
    call = subprocess.call('export LC_ALL=C.UTF-8; export LANG=C.UTF-8; . venv/bin/activate;pip install -r requirements.txt', cwd= ''.join([dstDir, 'subscribie']), shell=True)

    # Migrate the database
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + dstDir + 'data.db'
    upgrade(directory=dstDir + 'subscribie/migrations')

    # Seed users table with site owners email address & password so can login
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()
    email = payload['users'][0].lower()
    now = datetime.datetime.now()
    login_token = urlsafe_b64encode(os.urandom(24)).decode("utf-8")
    password = generate_password_hash(payload['password'])
    cur.execute("INSERT INTO user (email, password, created_at, active, login_token) VALUES (?,?,?,?,?)", (email, password, now, 1, login_token,))
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

    # Seed integration table
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()                                                   
    cur.execute("INSERT INTO integration (id) VALUES(1)") 
    con.commit()                                                         
    con.close()


    # Seed the plan table
    con = sqlite3.connect(dstDir + 'data.db')
    con.text_factory = str
    cur = con.cursor()                                                   
    now = datetime.datetime.now()
    title = payload['plans'][0]['title']
    archived = 0
    uuid = str(uuid4())
    interval_amount = payload['plans'][0]['interval_amount']
    interval_unit = payload['plans'][0]['interval_unit']
    if 'weekly' in interval_unit or 'monthly' in interval_unit or \
       'yearly' in interval_unit:
           pass
    else:
        interval_unit = 'monthly'
    sell_price = payload['plans'][0]['sell_price']

    cur.execute("""INSERT INTO plan 
                (created_at, archived, uuid, title, sell_price, interval_amount, 
                interval_unit) 
                VALUES (?,?,?,?,?,?,?)""", 
                (now, archived, uuid, title, sell_price, interval_amount,
                interval_unit))

    if interval_amount == 0:
        requires_subscription = 0
    else:
        requires_subscription = 1

    if sell_price == 0:
        requires_instant_payment = 0
    else:
        requires_instant_payment = 1
    
    # Item requirements
    cur.execute('''INSERT INTO plan_requirements (id , created_at, plan_id, 
                    instant_payment, subscription) 
                 VALUES ( 1, ?, 1, ?, ?)
                 ''', (now, requires_instant_payment, requires_subscription))
    # Item selling points
    selling_points = payload['plans'][0]['selling_points']

    points = []

    for i, point in enumerate(selling_points):
        now = datetime.datetime.now()
        points.append((i, now, selling_points[i], 1))

    cur.executemany('''INSERT INTO plan_selling_points 
                    (id, created_at, point, plan_id)
                    VALUES (?, ?, ?, ?)''', points)
    con.commit()                                                         
    con.close()
    
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
