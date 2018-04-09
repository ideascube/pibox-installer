import os
import argparse
import sys
import json
import yaml
import data
from backend import catalog
from run_installation import run_installation
from util import CancelEvent
from util import get_free_space_in_dir
from util import compute_space_required


def set_config(config, args):
    if not isinstance(config, dict):
            return

    # project_name
    if "project_name" in config:
        args.name = config.get("project_name")

    # language
    if "language" in config:
        args.language = config.get("language")

    # timezone
    if "timezone" in config:
        args.timezone = config.get("timezone")

    # wifi
    if "wifi" in config and isinstance(config["wifi"], dict):
        if "password" in config["wifi"]:
            if "protected" not in config["wifi"] \
                    or config["wifi"]["protected"]:
                args.wifi_pwd = config["wifi"]["password"]

    # admin account
    if "admin_account" in config \
            and isinstance(config["admin_account"], dict):
        if config["admin_account"].get("custom") is not None:

            # we need both login and password
            if config["admin_account"].get("login") is not None \
                    and config["admin_account"].get("password") is not None:
                args.admin_account = [config["admin_account"]["login"],
                                      config["admin_account"]["password"]]

    # branding
    if "branding" in config and isinstance(config["branding"], dict):
        if config["branding"].get("logo") is not None:
            args.logo = os.path.abspath(config["branding"]["logo"])

        if config["branding"].get("favicon") is not None:
            args.favicon = os.path.abspath(config["branding"]["favicon"])

        if config["branding"].get("css") is not None:
            args.css = os.path.abspath(config["branding"]["css"])

    # build_dir
    if config.get("build_dir") is not None:
        args.build_dir = os.path.abspath(config["build_dir"])

    if config.get("size") is not None:
        args.size = config["size"]

    # content
    if "content" in config and isinstance(config["content"], dict):

        if "kalite" in config["content"] \
                and isinstance(config["content"]["kalite"], list):
            args.kalite = config["content"]["kalite"]

        if "wikifundi" in config["content"] \
                and isinstance(config["content"]["wikifundi"], list):
            args.wikifundi = config["content"]["wikifundi"]

        if config["content"].get("edupi") is not None:
            args.edupi = config["content"]["edupi"]

        if config["content"].get("aflatoun") is not None:
            args.aflatoun = config["content"]["aflatoun"]

        if "zims" in config["content"] \
                and isinstance(config["content"]["zims"], list):
                args.zim_install = config["content"]["zims"]


class Logger:
    def step(step):
        print("\033[00;34m--> " + step + "\033[00m")

    def err(err):
        print("\033[00;31m" + err + "\033[00m")

    def raw_std(std):
        sys.stdout.write(std)

    def std(std):
        print(std)

try:
    catalogs = catalog.get_catalogs()
except Exception as exception:
    print(exception, file=sys.stderr)
    print("Catalog downloads failed, you may check your internet connection")
    exit(2)

zim_choices = []
for catalog in catalogs:
    for (key, value) in catalog["all"].items():
        zim_choices.append(key)

languages = [code for code, language in data.ideascube_languages]

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument("--language", help="language (en)", choices=languages, default="en")
parser.add_argument("--wifi-pwd", help="wifi password (Open)")
parser.add_argument("--kalite", help="install kalite", choices=["fr", "en", "er"], nargs="+")
parser.add_argument("--aflatoun", help="install aflatoun", action="store_true")
parser.add_argument("--wikifundi", help="install wikifundi", choices=["fr", "en"], nargs="+")
parser.add_argument("--edupi", help="install edupi", action="store_true")
parser.add_argument("--zim-install", help="install zim", choices=zim_choices, nargs="+")
parser.add_argument("--size", help="resize image in B (5*2**30)", type=float, default=5*2**30)
parser.add_argument("--favicon", help="set favicon")
parser.add_argument("--logo", help="set logo")
parser.add_argument("--css", help="set css style")
parser.add_argument("--build-dir", help="set build directory (default current)", default=".")
parser.add_argument("--catalog", help="show catalog and exit", action="store_true")
parser.add_argument("--admin-account", help="create admin account [LOGIN, PWD]", nargs=2)
parser.add_argument("--config", help="use a JSON config file to set parameters (superseeds cli parameters)")


args = parser.parse_args()

if args.config:
    try:
        with open(args.config, 'r') as fd:
            config = json.load(fd)
    except Exception:
        print("Failed to parse JSON file {}".format(args.config))
        exit(1)
    else:
        set_config(config, args)

if args.catalog:
    for catalog in catalogs:
        print(yaml.dump(catalog, default_flow_style=False, default_style=''))
    exit(0)

if args.admin_account:
    admin_account = { "login": args.admin_account[0], "pwd": args.admin_account[1] }
else:
    admin_account = None

print(admin_account)

build_free_space = get_free_space_in_dir(args.build_dir)
if build_free_space < args.size:
    print("Not enough space available at {} to build image".format(args.build_dir), file=sys.stderr)
    exit(1)

space_required = compute_space_required(
                catalog=catalogs,
                zim_list=args.zim_install,
                kalite=args.kalite,
                wikifundi=args.wikifundi,
                aflatoun=args.aflatoun,
                edupi=args.edupi)
if args.size < space_required:
    print("image size ({}) is not large enough for the content ({})".format(args.size, space_required), file=sys.stderr)
    exit(3)

cancel_event = CancelEvent()
try:
    error = run_installation(
            name=args.name,
            timezone=args.timezone,
            language=args.language,
            wifi_pwd=args.wifi_pwd,
            kalite=args.kalite,
            wikifundi=args.wikifundi,
            aflatoun=args.aflatoun,
            edupi=args.edupi,
            zim_install=args.zim_install,
            size=args.size,
            logger=Logger,
            cancel_event=cancel_event,
            sd_card=None,
            logo=args.logo,
            favicon=args.favicon,
            css=args.css,
            admin_account=admin_account,
            build_dir=args.build_dir)
except:
    cancel_event.cancel()
else:
    if error:
        print("Installation failed: " + str(error), file=sys.stderr)
    else:
        print("Installation succeded")
