#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import json


# machine must provide write_file and exec_cmd functions
def run(machine, name, timezone, wifi_pwd, edupi, wikifundi, aflatoun, kalite,
        zim_install, ansiblecube_path, admin_account):

    # install base packages
    machine.exec_cmd("sudo apt-get update")
    machine.exec_cmd("sudo apt-get install -y python-pip python-yaml "
                     "python-jinja2 python-httplib2 python-paramiko "
                     "python-pkg-resources libffi-dev libssl-dev git "
                     "lsb-release exfat-fuse")
    machine.exec_cmd("sudo pip install ansible==2.2.0")

    # prepare ansible files
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
    machine.exec_cmd("sudo cp {path}/hosts /etc/ansible/hosts"
                     .format(path=ansiblecube_path))
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible/facts.d")

    extra_vars = {
        'project_name': name,
        'timezone': timezone,
    }

    ansible_args = "--inventory hosts"
    ansible_args += " --tags master,configure"
    ansible_args += " --extra-vars \"%s\"" % json.dumps(extra_vars)
    ansible_args += " main.yml"

    ansible_cmd = (
        "sudo sh -c 'cd {} && /usr/local/bin/ansible-playbook {}'"
        .format(ansiblecube_path, ansible_args))

    machine.exec_cmd(ansible_cmd)
