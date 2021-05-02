import os
import errno
import shutil
import re
import subprocess
from flask import Flask, request
from werkzeug.security import generate_password_hash
import json
import sqlite3
import datetime
from base64 import urlsafe_b64encode
from pathlib import Path
from flask_sqlalchemy import SQLAlchemy
from uuid import uuid4
import logging
import tempfile

logging.basicConfig(level="DEBUG")

app = Flask(__name__)

db = SQLAlchemy()
db.init_app(app)

# Load .env settings
curDir = os.path.dirname(os.path.realpath(__file__))
app.config.from_pyfile("/".join([curDir, ".env"]))


def sed_inplace(filename, pattern, repl):
    """
    Perform the pure-Python equivalent of in-place `sed` substitution: e.g.,
    `sed -i -e 's/'${pattern}'/'${repl}' "${filename}"`.
    Credit: Cecil Curry https://stackoverflow.com/a/31499114
    """
    # For efficiency, precompile the passed regular expression.
    pattern_compiled = re.compile(pattern)

    # For portability, NamedTemporaryFile() defaults to mode "w+b" (i.e., binary  # noqa
    # writing with updating). This is usually a good thing. In this case,  # noqa
    # however, binary writing imposes non-trivial encoding constraints trivially  # noqa
    # resolved by switching to text writing. Let's do that.
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        with open(filename) as src_file:
            for line in src_file:
                tmp_file.write(pattern_compiled.sub(repl, line))

    # Overwrite the original file with the munged temporary file in a
    # manner preserving file attributes (e.g., permissions).
    shutil.copystat(filename, tmp_file.name)
    shutil.move(tmp_file.name, filename)


@app.route("/", methods=["GET", "POST"])
@app.route("/deploy", methods=["GET", "POST"])
def deploy():
    logging.info("New site request recieved")
    payload = json.loads(request.data)
    filename = re.sub(r"\W+", "", payload["company"]["name"])
    webaddress = filename.lower() + "." + app.config["SUBSCRIBIE_DOMAIN"]
    # Create directory for site
    try:
        dstDir = app.config["SITES_DIRECTORY"] + webaddress + "/"
        if Path(dstDir).exists():
            print("Site {} already exists. Exiting...".format(webaddress))
            exit()
        os.mkdir(dstDir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        # Create .env file from .env.example
        envFileSrc = Path(
            app.config["SUBSCRIBIE_REPO_DIRECTORY"] + "/.env.example"
        )  # noqa E501
        envFileDst = Path(dstDir + "/.env")
        shutil.copy(envFileSrc, envFileDst)

        # Set SUBSCRIBIE_REPO_DIRECTORY for subscribie site deployment
        # Note that the deployer also has the same env value set.
        SUBSCRIBIE_REPO_DIRECTORY = app.config["SUBSCRIBIE_REPO_DIRECTORY"]
        subprocess.call(
            f"dotenv -f {envFileDst} set SUBSCRIBIE_REPO_DIRECTORY {SUBSCRIBIE_REPO_DIRECTORY}",  # noqa
            shell=True,  # noqa E501
        )

        # Generate RSA keys for jwt auth
        subprocess.call(
            f'ssh-keygen -t rsa -N "" -f {dstDir}id_rsa', shell=True
        )  # noqa E501

        # Update .env values for public & private keys
        privateKeyDst = dstDir + "id_rsa"
        subprocess.call(
            f"dotenv -f {envFileDst} set PRIVATE_KEY {privateKeyDst}",
            shell=True,  # noqa E501
        )

        publicKeyDst = dstDir + "id_rsa.pub"
        subprocess.call(
            f"dotenv -f {envFileDst} set PUBLIC_KEY {publicKeyDst}", shell=True
        )

        # Set SERVER_NAME in .env
        subprocess.call(
            f"dotenv -f {envFileDst} set SERVER_NAME {webaddress}", shell=True
        )

        # Create custom_pages path
        custom_pages_path = Path(dstDir + "/custom_pages/")
        # Set CUSTOM_PAGES_PATH in .env
        subprocess.call(
            f"dotenv -f {envFileDst} set CUSTOM_PAGES_PATH {custom_pages_path}",
            shell=True,
        )
        if Path(custom_pages_path).exists() is False:
            os.mkdir(custom_pages_path)

        # Template base dir
        TEMPLATE_BASE_DIR = Path(
            app.config["SUBSCRIBIE_REPO_DIRECTORY"] + "/subscribie/themes/"
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set TEMPLATE_BASE_DIR {TEMPLATE_BASE_DIR}",  # noqa: E501
            shell=True,
        )

        # Set HONEYCOMB_API_KEY connect env settings
        subprocess.call(
            f"dotenv -f {envFileDst} set HONEYCOMB_API_KEY {app.config['HONEYCOMB_API_KEY']}",  # noqa: E501
            shell=True,
        )

        #
        subprocess.call(
            f"dotenv -f {envFileDst} set HONEYCOMB_API_KEY {app.config['HONEYCOMB_API_KEY']}",  # noqa: E501
            shell=True,
        )

        # Set DB PATH & SQLALCHEMY URI
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + dstDir + "data.db"

        subprocess.call(
            f"dotenv -f {envFileDst} set SQLALCHEMY_DATABASE_URI {SQLALCHEMY_DATABASE_URI}",  # noqa: E501
            shell=True,
        )

        DB_FULL_PATH = dstDir + "data.db"

        subprocess.call(
            f"dotenv -f {envFileDst} set DB_FULL_PATH {DB_FULL_PATH}",
            shell=True,
        )

        # Set Stripe keys for Stripe connect live mode
        subprocess.call(
            f"dotenv -f {envFileDst} set STRIPE_LIVE_SECRET_KEY {app.config['STRIPE_LIVE_SECRET_KEY']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set STRIPE_LIVE_PUBLISHABLE_KEY {app.config['STRIPE_LIVE_PUBLISHABLE_KEY']}",  # noqa: E501
            shell=True,
        )
        # Set Stripe keys for Stripe connect test mode
        subprocess.call(
            f"dotenv -f {envFileDst} set STRIPE_TEST_SECRET_KEY {app.config['STRIPE_TEST_SECRET_KEY']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set STRIPE_TEST_PUBLISHABLE_KEY {app.config['STRIPE_TEST_PUBLISHABLE_KEY']}",  # noqa: E501
            shell=True,
        )

        # Update .env values for mail
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_SERVER {app.config['MAIL_SERVER']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_PORT {app.config['MAIL_PORT']}",
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_PORT {app.config['MAIL_PORT']}",
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_USERNAME {app.config['MAIL_USERNAME']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_PASSWORD {app.config['MAIL_PASSWORD']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_DEFAULT_SENDER {app.config['EMAIL_LOGIN_FROM']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set MAIL_USE_TLS {app.config['MAIL_USE_TLS']}",  # noqa: E501
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set EMAIL_LOGIN_FROM {app.config['EMAIL_LOGIN_FROM']}",  # noqa: E501
            shell=True,
        )

        uploadImgDst = Path(dstDir + "/uploads/")
        os.makedirs(uploadImgDst, exist_ok=True)
        uploadedFilesDst = Path(dstDir + "/uploads/")
        os.makedirs(uploadedFilesDst, exist_ok=True)
        subprocess.call(
            f"dotenv -f {envFileDst} set UPLOADED_IMAGES_DEST {uploadImgDst}",
            shell=True,
        )
        subprocess.call(
            f"dotenv -f {envFileDst} set UPLOADED_FILES_DEST {uploadedFilesDst}",  # noqa: E501
            shell=True,
        )

        successRedirectUrl = "https://" + webaddress + "/complete_mandate"
        subprocess.call(
            f"dotenv -f {envFileDst} set SUCCESS_REDIRECT_URL {successRedirectUrl}",  # noqa: E501
            shell=True,
        )

        thankyouUrl = "https://" + webaddress + "/thankyou"
        subprocess.call(
            f"dotenv -f {envFileDst} set THANKYOU_URL {thankyouUrl}",
            shell=True,  # noqa: E501
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set STRIPE_CONNECT_ACCOUNT_ANNOUNCER_HOST {app.config['STRIPE_CONNECT_ACCOUNT_ANNOUNCER_HOST']}",  # noqa: E501
            shell=True,
        )

        # Set env config for Google oauth signin/up
        subprocess.call(
            f"dotenv -f {envFileDst} set GOOGLE_CLIENT_ID {app.config['GOOGLE_CLIENT_ID']}",  # noqa: E501
            shell=True,
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set GOOGLE_CLIENT_SECRET {app.config['GOOGLE_CLIENT_SECRET']}",  # noqa: E501
            shell=True,
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set GOOGLE_REDIRECT_URI {webaddress}/google-oauth2callback/",  # noqa: E501
            shell=True,
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set GOOGLE_RESPONSE_TYPE {app.config['GOOGLE_RESPONSE_TYPE']}",  # noqa: E501
            shell=True,
        )

        subprocess.call(
            f"dotenv -f {envFileDst} set GOOGLE_SCOPE '{app.config['GOOGLE_SCOPE']}'",  # noqa: E501
            shell=True,
        )

    except KeyError as e:
        print(f"KeyError missing config? {e}")

    except Exception as e:
        print("Did not clone subscribie for some reason")
        print(e, e.args)
        pass

    # Migrate the database
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + dstDir + "data.db"

    # Copy over empty db schema
    shutil.copy(
        Path(app.config["SUBSCRIBIE_REPO_DIRECTORY"] + "/data.db"), dstDir
    )  # noqa: E501

    # Seed users table with site owners email address & password so can login
    con = sqlite3.connect(dstDir + "data.db")
    con.text_factory = str
    cur = con.cursor()
    email = payload["users"][0].lower()
    now = datetime.datetime.now()
    login_token = urlsafe_b64encode(os.urandom(24)).decode("utf-8")
    password = generate_password_hash(payload["password"])
    cur.execute(
        "INSERT INTO user (email, password, created_at, active, login_token) VALUES (?,?,?,?,?)",  # noqa: E501
        (
            email,
            password,
            now,
            1,
            login_token,
        ),
    )
    cur.execute("INSERT INTO payment_provider (stripe_active) VALUES(0)")  # noqa: E501
    con.commit()
    con.close()

    # Seed company table
    con = sqlite3.connect(dstDir + "data.db")
    con.text_factory = str
    cur = con.cursor()
    now = datetime.datetime.now()
    company_name = payload["company"]["name"]
    cur.execute(
        "INSERT INTO company (created_at, name) VALUES (?,?)",
        (now, company_name),  # noqa: E501
    )
    con.commit()
    con.close()

    # Seed integration table
    con = sqlite3.connect(dstDir + "data.db")
    con.text_factory = str
    cur = con.cursor()
    cur.execute("INSERT INTO integration (id) VALUES(1)")
    con.commit()
    con.close()

    # Seed the plan table
    con = sqlite3.connect(dstDir + "data.db")
    con.text_factory = str
    cur = con.cursor()
    now = datetime.datetime.now()
    title = payload["plans"][0]["title"]
    description = payload["plans"][0]["description"].strip()
    if description == "":
        description = None
    archived = 0
    uuid = str(uuid4())
    interval_amount = payload["plans"][0]["interval_amount"]
    interval_unit = payload["plans"][0]["interval_unit"]
    if (
        "weekly" in interval_unit
        or "monthly" in interval_unit
        or "yearly" in interval_unit
    ):
        pass
    else:
        interval_unit = "monthly"
    sell_price = payload["plans"][0]["sell_price"]

    cur.execute(
        """INSERT INTO plan
                (created_at, archived, uuid,
                title,
                description,
                sell_price,
                interval_amount,
                interval_unit,
                trial_period_days,
                private)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            now,
            archived,
            uuid,
            title,
            description,
            sell_price,
            interval_amount,
            interval_unit,
            0,
            0,
        ),  # noqa: E501
    )

    if interval_amount == 0:
        requires_subscription = 0
    else:
        requires_subscription = 1

    if sell_price == 0:
        requires_instant_payment = 0
    else:
        requires_instant_payment = 1

    # Item requirements
    cur.execute(
        """INSERT INTO plan_requirements (id , created_at, plan_id,
                    instant_payment, subscription)
                 VALUES ( 1, ?, 1, ?, ?)
                 """,
        (now, requires_instant_payment, requires_subscription),
    )

    points = []
    for i in range(3):
        points.append((i, datetime.datetime.now(), f"Point {i}", 1))

    cur.executemany(
        """INSERT INTO plan_selling_points
                    (id, created_at, point, plan_id)
                    VALUES (?, ?, ?, ?)""",
        points,
    )
    con.commit()
    con.close()

    # Begin uwsgi vassal config creation
    # Open application skeleton (app.skel) file and append
    # "subscribe-to = <website-hostname>" config entry for the new
    # sites webaddress so that uwsgi's fastrouter can route the hostname.
    # Also add cron2 = minute=-1 curl -L <webaddress>/admin/announce-stripe-connect  # noqa: E501
    # So that site will announce its stipe connect account id
    curDir = os.path.dirname(os.path.realpath(__file__))

    # Copy app.skel to <webaddress>.ini
    vassalConfigFile = Path(dstDir + "/" + webaddress + ".ini")
    shutil.copy(Path(curDir + "/" + "app.skel"), vassalConfigFile)

    sed_inplace(
        vassalConfigFile,
        r"subscribe-to.*",
        f"subscribe-to = /tmp/sock2:{webaddress}\n",  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"cron2.*announce-stripe-connect",
        fr"cron2 = minute=-1 curl -L {webaddress}\/admin\/announce-stripe-connect\n",  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"cron2.*refresh-subscription-statuses",
        fr"cron2 = minute=-10 curl -L {webaddress}\/admin\/refresh-subscription-statuses\n",  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"^virtualenv.*",
        fr'virtualenv = {app.config["PYTHON_VENV_DIRECTORY"]}\n',  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"^env.*",
        f'env = PYTHON_PATH_INJECT={app.config["SUBSCRIBIE_REPO_DIRECTORY"]}\n',  # noqa: E501
    )

    wsgiFile = Path(
        app.config["SUBSCRIBIE_REPO_DIRECTORY"] + "/subscribie.wsgi"
    )  # noqa: E501
    sed_inplace(
        vassalConfigFile,
        r"wsgi-file.*",
        f"wsgi-file = {wsgiFile}\n",
    )

    login_url = "".join(["https://", webaddress, "/auth/login/", login_token])

    return login_url


application = app
