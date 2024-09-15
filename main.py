import os
from dotenv import load_dotenv
import errno
import shutil
import re
import subprocess
from werkzeug.security import generate_password_hash
import sqlite3
import datetime
from pathlib import Path
from uuid import uuid4
import logging
import tempfile

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.responses import PlainTextResponse

load_dotenv(verbose=True)
logging.basicConfig(level="DEBUG")


class EnvSettings(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        logging.info(f"Setting key: {key}, to value {value}")


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


async def deploy(request):
    logging.info("New site request recieved")
    payload = await request.json()
    filename = re.sub(r"\W+", "", payload["company"]["name"])
    webaddress = filename.lower() + "." + os.getenv("SUBSCRIBIE_DOMAIN")
    # Country code list
    supported_countries_list = {
        "US",
        "GB",
        "AT",
        "BE",
        "CY",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PT",
        "SK",
        "SI",
        "ES",
    }
    default_country_code = payload.get("country_code")
    # country code
    if (
        default_country_code is None
        or default_country_code not in supported_countries_list
    ):
        default_country_code = "US"
        logging.warning("Defaulting to country_code US")

    # Determin default currency
    country_to_currency_code = {
        "US": "USD",
        "GB": "GBP",
        "AT": "EUR",
        "BE": "EUR",
        "CY": "EUR",
        "EE": "EUR",
        "FI": "EUR",
        "FR": "EUR",
        "DE": "EUR",
        "GR": "EUR",
        "IE": "EUR",
        "IT": "EUR",
        "LV": "EUR",
        "LT": "EUR",
        "LU": "EUR",
        "MT": "EUR",
        "NL": "EUR",
        "PT": "EUR",
        "SK": "EUR",
        "SI": "EUR",
        "ES": "EUR",
    }
    default_currency = country_to_currency_code[default_country_code]

    # Create directory for site
    try:
        dstDir = os.getenv("SITES_DIRECTORY") + webaddress + "/"
        logging.debug(f"dstDir is set to {dstDir}")
        if Path(dstDir).exists():
            msg = f"Site {webaddress} already exists. Exiting..."
            logging.warning(msg)
            response = JSONResponse({msg: msg})
            return response
        os.mkdir(dstDir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    try:
        # Create .env file from .env.example
        envFileSrc = Path(
            os.getenv("SUBSCRIBIE_REPO_DIRECTORY") + "/.envsubst.template"
        )  # noqa E501
        logging.debug(f"envFileSrc is: {envFileSrc}")

        envFileDst = Path(dstDir + "/.env")
        logging.debug(f"envFileDst is: {envFileDst}")
        shutil.copy(envFileSrc, envFileDst)
        # Build envSettings vars
        envSettings = EnvSettings()
        envSettings["FLASK_ENV"] = os.getenv("FLASK_ENV")
        envSettings["PERMANENT_SESSION_LIFETIME"] = os.getenv(
            "PERMANENT_SESSION_LIFETIME"
        )
        envSettings["SENTRY_SDK_DSN"] = os.getenv(
            "SENTRY_SDK_DSN"
        )
        envSettings["SENTRY_SDK_SESSION_REPLAY_ID"] = os.getenv(
            "SENTRY_SDK_SESSION_REPLAY_ID"
        )
        envSettings[
            "SUBSCRIBIE_REPO_DIRECTORY"
        ] = f"{os.getenv('SUBSCRIBIE_REPO_DIRECTORY')}"

        envSettings["SERVER_NAME"] = webaddress

        custom_pages_path = Path(dstDir + "/custom_pages/")
        envSettings["CUSTOM_PAGES_PATH"] = custom_pages_path

        if Path(custom_pages_path).exists() is False:
            os.mkdir(custom_pages_path)

        envSettings[
            "TEMPLATE_BASE_DIR"
        ] = f"{Path(os.getenv('SUBSCRIBIE_REPO_DIRECTORY'))}/subscribie/themes/"  # noqa: E501

        envSettings["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{dstDir}data.db"
        envSettings["DB_FULL_PATH"] = f"{dstDir}data.db"

        envSettings[
            "STRIPE_LIVE_SECRET_KEY"
        ] = f"{os.getenv('STRIPE_LIVE_SECRET_KEY')}"  # noqa: E501

        envSettings[
            "STRIPE_LIVE_PUBLISHABLE_KEY"
        ] = f"{os.getenv('STRIPE_LIVE_PUBLISHABLE_KEY')}"

        envSettings[
            "STRIPE_TEST_SECRET_KEY"
        ] = f"{os.getenv('STRIPE_TEST_SECRET_KEY')}"  # noqa: E501

        envSettings[
            "STRIPE_TEST_PUBLISHABLE_KEY"
        ] = f"{os.getenv('STRIPE_TEST_PUBLISHABLE_KEY')}"

        envSettings[
            "MAIL_DEFAULT_SENDER"
        ] = f"{os.getenv('EMAIL_LOGIN_FROM')}"  # noqa: E501

        envSettings["EMAIL_LOGIN_FROM"] = f"{os.getenv('EMAIL_LOGIN_FROM')}"

        envSettings[
            "EMAIL_QUEUE_FOLDER"
        ] = f"{os.getenv('EMAIL_QUEUE_FOLDER')}"  # noqa: E501

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
        ] = f"{os.getenv('STRIPE_CONNECT_ACCOUNT_ANNOUNCER_HOST')}"

        envSettings["SAAS_URL"] = os.getenv("SAAS_URL")
        envSettings["SAAS_API_KEY"] = os.getenv("SAAS_API_KEY")
        envSettings["SAAS_ACTIVATE_ACCOUNT_PATH"] = os.getenv(
            "SAAS_ACTIVATE_ACCOUNT_PATH"
        )

        envSettings["TELEGRAM_TOKEN"] = os.getenv("TELEGRAM_TOKEN")

        envSettings["TELEGRAM_CHAT_ID"] = os.getenv("TELEGRAM_TOKEN")

        envSettings["TELEGRAM_PYTHON_LOG_LEVEL"] = os.getenv(
            "TELEGRAM_PYTHON_LOG_LEVEL"
        )
        envSettings["PATH_TO_SITES"] = os.getenv("PATH_TO_SITES")

        envSettings["PATH_TO_RENAME_SCRIPT"] = os.getenv(
            "PATH_TO_RENAME_SCRIPT"
        )  # noqa: E501

        envSettings["SUPPORTED_CURRENCIES"] = os.getenv(
            "SUPPORTED_CURRENCIES"
        )  # noqa: E501

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
        Path(os.getenv("SUBSCRIBIE_REPO_DIRECTORY") + "/data.db"), dstDir
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
    # Set default_currency
    cur.execute(
        "INSERT INTO setting (default_currency, default_country_code) VALUES (?,?)",
        (
            default_currency,
            default_country_code,
        ),  # noqa: E501
    )  # noqa: E501

    # Seed company table
    now = datetime.datetime.now()
    company_name = payload["company"]["name"]
    cur.execute(
        "INSERT INTO company (created_at, name) VALUES (?,?)",
        (now, company_name),  # noqa: E501
    )
    # Seed integration table
    cur.execute("INSERT INTO integration (id) VALUES(1)")

    # Seed the plan table
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
        rf"cron2 = minute=-1 curl -L {webaddress}\/admin\/announce-stripe-connect\n",  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"cron2.*refresh-subscription-statuses",
        rf"cron2 = minute=-10 curl -L {webaddress}\/admin\/refresh-subscription-statuses\n",  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"^virtualenv.*",
        rf'virtualenv = {os.getenv("PYTHON_VENV_DIRECTORY")}\n',  # noqa: E501
    )

    sed_inplace(
        vassalConfigFile,
        r"^env.*",
        f'env = PYTHON_PATH_INJECT={os.getenv("SUBSCRIBIE_REPO_DIRECTORY")}\n',  # noqa: E501
    )

    wsgiFile = Path(
        os.getenv("SUBSCRIBIE_REPO_DIRECTORY") + "/subscribie.wsgi"
    )  # noqa: E501
    sed_inplace(
        vassalConfigFile,
        r"wsgi-file.*",
        f"wsgi-file = {wsgiFile}\n",
    )

    login_url = "".join(["https://", webaddress, "/auth/login/", login_token])

    return PlainTextResponse(login_url)


routes = [
    Route("/", endpoint=deploy, methods=["GET", "POST"]),
    Route("/deploy", endpoint=deploy, methods=["GET", "POST"]),
]

app = Starlette(routes=routes)
