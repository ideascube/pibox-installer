#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import json
import tempfile

from data import mirror
from backend.catalog import CATALOGS

ansiblecube_path = "/var/lib/ansible/local"


def run(machine, tags, extra_vars={}, secret_keys=[]):

    # predefined defaults we want to superseed whichever in ansiblecube
    ansible_vars = {
        'mirror': mirror,
        'catalogs': CATALOGS,
    }
    ansible_vars.update(extra_vars)

    # save extra_vars to a file on guest
    extra_vars_path = os.path.join(ansiblecube_path, "extra_vars.json")
    with tempfile.NamedTemporaryFile('w', delete=False) as fp:
        json.dump(ansible_vars, fp, indent=4)
        fp.close()
        machine.put_file(fp.name, extra_vars_path)
        os.unlink(fp.name)

    # prepare ansible command
    ansible_cmd = ('/usr/local/bin/ansible-playbook -vvv '
                   ' --inventory hosts'
                   ' --tags {tags}'
                   ' --extra-vars="@{ev_path}"'
                   ' main.yml'
                   .format(tags=",".join(tags), ev_path=extra_vars_path))

    ansible_pull_cmd = ("sudo sh -c 'cd {path} && {cmd}'"
                        .format(path=ansiblecube_path, cmd=ansible_cmd))

    # display sent configuration to logger
    machine._logger.std("ansiblecube extra_vars")
    machine._logger.raw_std(
        json.dumps({k: '****' if k in secret_keys else v
                    for k, v in ansible_vars.items()}, indent=4))

    machine.exec_cmd(ansible_pull_cmd)


def run_for_image(machine, seal=False):

    tags = ['master', 'rename', 'configure']
    if seal:
        tags.append('seal')

    machine.exec_cmd("sudo apt-get update")

    machine.exec_cmd("sudo apt-get install -y python-pip python-yaml "
                     "python-jinja2 python-httplib2 python-paramiko "
                     "python-pkg-resources libffi-dev libssl-dev git "
                     "lsb-release exfat-utils")
    machine.exec_cmd("sudo pip install ansible==2.2.0")

    # prepare ansible files
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
    machine.exec_cmd("sudo cp {path}/hosts /etc/ansible/hosts"
                     .format(path=ansiblecube_path))
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible/facts.d")

    extra_vars = {'project_name': "default", 'timezone': "UTC"}

    run(machine, tags, extra_vars)


def build_extra_vars(name, timezone, language, language_name, wifi_pwd,
                     edupi, wikifundi_languages,
                     aflatoun_languages, kalite_languages, packages,
                     admin_account,
                     root_partition_size, disk_size):

    extra_vars = {
        'root_partition_size': root_partition_size // 2 ** 30,
        'disk_size': disk_size // 2 ** 30,
        'project_name': name,
        'timezone': timezone,
        'language': language,
        'language_name': language_name,
        'kalite_languages': kalite_languages,
        'wikifundi_languages': wikifundi_languages,
        'aflatoun_languages': aflatoun_languages,
        'edupi': edupi,
        'packages': [{"name": x, "status": "present"} for x in packages],
        'captive_portal': True,
        'custom_branding_path': '/tmp',
        'admin_account': "admin",
        'admin_password': "admin",
    }

    if wifi_pwd:
        extra_vars.update({'wpa_pass': wifi_pwd})

    if admin_account is not None:
        extra_vars.update({'admin_account': admin_account['login'],
                           'admin_password': admin_account['pwd']})
        secret_keys = ['admin_account', 'admin_password']
    else:
        secret_keys = []

    return extra_vars, secret_keys


def run_phase_one(machine, extra_vars, secret_keys,
                  logo=None, favicon=None, css=None,):

    tags = ['resize', 'rename', 'configure']

    # copy branding files if set
    branding = {'favicon.png': favicon,
                'header-logo.png': logo, 'style.css': css}

    for fname, item in [(k, v) for k, v in branding.items() if v is not None]:
        has_custom_branding = True
        machine.put_file(item, "/tmp/{}".format(fname))

    extra_vars.update({'has_custom_branding': has_custom_branding})

    run(machine, tags, extra_vars, secret_keys)


def run_phase_two(machine, extra_vars, secret_keys, seal=False):
    tags = ['move-content']
    if seal:
        tags.append('seal')

    run(machine, tags, extra_vars, secret_keys)
