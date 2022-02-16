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
            app.config["SUBSCRIBIE_REPO_DIRECTORY"] + "/.envsubst.template"
        )  # noqa E501
        envFileDst = Path(dstDir + "/.env")
        shutil.copy(envFileSrc, envFileDst)
        # Build envSettings vars
        envSettings = {}

        envSettings[
            "SUBSCRIBIE_REPO_DIRECTORY"
        ] = f"{app.config['SUBSCRIBIE_REPO_DIRECTORY']}"

        envSettings["SERVER_NAME"] = webaddress

        custom_pages_path = Path(dstDir + "/custom_pages/")
        envSettings["CUSTOM_PAGES_PATH"] = custom_pages_path

        if Path(custom_pages_path).exists() is False:
            os.mkdir(custom_pages_path)

        envSettings[
            "TEMPLATE_BASE_DIR"
        ] = f"{Path(app.config['SUBSCRIBIE_REPO_DIRECTORY'])}/subscribie/themes/"  # noqa: E501

        envSettings["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{dstDir}data.db"
        envSettings["DB_FULL_PATH"] = f"{dstDir}data.db"

        envSettings[
            "STRIPE_LIVE_SECRET_KEY"
        ] = f"{app.config['STRIPE_LIVE_SECRET_KEY']}"

        envSettings[
            "STRIPE_LIVE_PUBLISHABLE_KEY"
        ] = f"{app.config['STRIPE_LIVE_PUBLISHABLE_KEY']}"

        envSettings[
            "STRIPE_TEST_SECRET_KEY"
        ] = f"{app.config['STRIPE_TEST_SECRET_KEY']}"

        envSettings[
            "STRIPE_TEST_PUBLISHABLE_KEY"
        ] = f"{app.config['STRIPE_TEST_PUBLISHABLE_KEY']}"

        envSettings[
            "MAIL_DEFAULT_SENDER"
        ] = f"{app.config['EMAIL_LOGIN_FROM']}"  # noqa: E501

        envSettings["MAIL_LOGIN_FROM"] = f"{app.config['EMAIL_LOGIN_FROM']}"

        envSettings[
            "MAIL_QUEUE_FOLDER"
        ] = f"{app.config['EMAIL_QUEUE_FOLDER']}"  # noqa: E501

        uploadImgDst = Path(dstDir + "/uploads/")
        os.makedirs(uploadImgDst, exist_ok=True)
        uploadedFilesDst = Path(dstDir + "/uploads/")
        os.makedirs(uploadedFilesDst, exist_ok=True)

        envSettings["UPLOADED_IMAGES_DEST"] = uploadImgDst
        envSettings["UPLOADED_FILES_DEST"] = uploadedFilesDst

        successRedirectUrl = "https://" + webaddress + "/complete_mandate"
        envSettings["SUCCESS_REDIRECT_URL"] = successRedirectUrl

        thankyouUrl = "https://" + webaddress + "/thankyou"
        envSettings["THANKYOU_URL"] = thankyouUrl

        envSettings[
            "STRIPE_CONNECT_ACCOUNT_ANNOUNCER_HOST"
        ] = f"{app.config['STRIPE_CONNECT_ACCOUNT_ANNOUNCER_HOST']}"

        envSettings["SAAS_URL"] = app.config["SAAS_URL"]
        envSettings["SAAS_API_KEY"] = app.config["SAAS_API_KEY"]
        envSettings["SAAS_ACTIVATE_ACCOUNT_PATH"] = app.config[
            "SAAS_ACTIVATE_ACCOUNT_PATH"
        ]

        envSettings["TELEGRAM_TOKEN"] = app.config["TELEGRAM_TOKEN"]

        envSettings["TELEGRAM_CHAT_ID"] = app.config["TELEGRAM_TOKEN"]

        envSettings["TELEGRAM_PYTHON_LOG_LEVEL"] = app.config[
            "TELEGRAM_PYTHON_LOG_LEVEL"
        ]

        envVars = "\n".join(map(str, envSettings))
        my_env = {**os.environ.copy(), **envSettings}  # Merge dicts
        subprocess.run(
            f"export $(xargs <{envVars}; cat {envFileSrc} | envsubst > {dstDir}.env)",  # noqa: E501
            shell=True,
            env=my_env,
        )

    except KeyError as e:
        print(f"KeyError missing config? {e}")

    except Exception as e:
        print("Did not clone subscribie for some reason")
        print(e, e.args)
        pass

    # Migrate the database
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
    password = generate_password_hash(payload["password"])
    try:
        login_token = payload["login_token"]
    except KeyError as e:
        login_token = ""
        logging.error(f"load_token not sent. {e}")
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
    cur.execute("UPDATE user set login_token = ?", (login_token,))  # noqa: E501
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
    try:
        description = payload["plans"][0]["description"].strip()
    except KeyError:
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
