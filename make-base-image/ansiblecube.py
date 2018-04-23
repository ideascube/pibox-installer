#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import json


# machine must provide write_file and exec_cmd functions
def run(machine, name, timezone, wifi_pwd, edupi, wikifundi, aflatoun, kalite,
        zim_install, ansiblecube_path, admin_account):
    machine.exec_cmd("sudo apt-get update")
    machine.exec_cmd("sudo apt-get install -y python-pip python-yaml "
                     "python-jinja2 python-httplib2 python-paramiko "
                     "python-pkg-resources libffi-dev libssl-dev git "
                     "lsb-release exfat-fuse")
    machine.exec_cmd("sudo pip install ansible==2.2.0")

    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
    machine.exec_cmd("sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

    hostname = name.replace("_", "-")

    machine.exec_cmd("sudo hostname %s" % hostname)
    machine.exec_cmd("sudo sh -c 'echo \"127.0.0.1   {host}\" >> /etc/hosts'"
                     .format(host=hostname))

    package_management = [{"name": x, "status": "present"}
                          for x in zim_install]
    device_list = {hostname: {
        "kalite": {
            "activated": str(kalite is not None),
            "version": "0.16.9",
            "language": kalite or [],
        },
        "wikifundi": {
            "activated": str(wikifundi is not None),
            "language": wikifundi or [],
        },
        "aflatoun": {
            "activated": aflatoun,
        },
        "edupi": {
            "activated": edupi,
        },
        "package_management": package_management,
        "portal": {
            "activated": True,
        }
    }}

    facts_dir = "/etc/ansible/facts.d"
    facts_path = facts_dir + "/device_list.fact"

    machine.exec_cmd("sudo mkdir --mode 0755 -p %s" % facts_dir)
    machine.exec_cmd(
        "sudo sh -c 'cat > {} <<END_OF_CMD3267\n{}\nEND_OF_CMD3267'"
        .format(facts_path, json.dumps(device_list, indent=4)))

    extra_vars = "project_name=%s" % name
    extra_vars += " timezone=%s" % timezone
    if wifi_pwd:
        extra_vars += " wpa_pass=%s" % wifi_pwd
    extra_vars += " own_config_file=True"
    if admin_account is not None:
        extra_vars += " admin_account='{login}' admin_password='{pwd}'"

    ansible_args = "--inventory hosts"
    ansible_args += " --tags master"
    ansible_args += " --extra-vars \"%s\"" % extra_vars
    ansible_args += " main.yml"

    ansible_pull_cmd = "sudo sh -c 'cd {} " \
        "&& /usr/local/bin/ansible-playbook {}'" \
        .format(ansiblecube_path, ansible_args)

    if admin_account is not None:
        run_ansible_pull_cmd = ansible_pull_cmd.format(**admin_account)
        displayed_ansible_pull_cmd = ansible_pull_cmd.format(login='****',
                                                             pwd='****')
    else:
        run_ansible_pull_cmd = displayed_ansible_pull_cmd = ansible_pull_cmd

    machine.exec_cmd(run_ansible_pull_cmd, displayed_ansible_pull_cmd)
