import os
import json

ansiblecube_path = "/var/lib/ansible/local"


def run(machine, tags, extra_vars={}, secret_kwargs={}):
    ''' machine must provide write_file and exec_cmd functions '''

    # TODO: move this to a more appropriate location
    #   simple shortcut to set tld for online demo
    if 'PIBOX_DEMO' in os.environ:
        extra_vars.update({'tld': 'kiwix.ml',
                           'project_name': 'demo'})

    machine.exec_cmd("sudo apt-get update")

    ansible_args = "--inventory hosts"
    ansible_args += " --tags {}".format(",".join(tags))
    ansible_args += " --extra-vars \"{}\"".format(
        json.dumps(extra_vars).replace('"', '\\"'))
    ansible_args += " main.yml"

    ansible_pull_cmd = (
        "sudo sh -c 'cd {} && /usr/local/bin/ansible-playbook {}'"
        .format(ansiblecube_path, ansible_args))

    if secret_kwargs:
        run_ansible_pull_cmd = ansible_pull_cmd.format(**secret_kwargs)
        displayed_ansible_pull_cmd = ansible_pull_cmd.format(
            **{k: '****' for k, v in secret_kwargs.items()})
    else:
        run_ansible_pull_cmd = displayed_ansible_pull_cmd = ansible_pull_cmd

    machine.exec_cmd(run_ansible_pull_cmd, displayed_ansible_pull_cmd)


def run_for_image(machine, seal=False):

    tags = ['master', 'resize', 'rename', 'configure']
    if seal:
        tags.append('seal')

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

    extra_vars = {'project_name': "default", 'timezone': "UTC"}

    run(machine, tags, extra_vars)


def run_for_user(machine, name, timezone, language, language_name, wifi_pwd,
                 edupi, wikifundi, aflatoun, kalite, zim_install,
                 admin_account, logo=None, favicon=None, css=None, seal=False):

    tags = ['resize', 'rename', 'configure', 'download-content']
    if seal:
        tags.append('seal')

    branding = {'favicon.png': favicon,
                'header-logo.png': logo, 'style.css': css}

    for fname, item in [(k, v) for k, v in branding.items() if v is not None]:
        has_custom_branding = True
        machine.put_file(item, "/tmp/{}".format(fname))

    extra_vars = {
        'project_name': name,
        'timezone': timezone,
        'language': language,
        'language_name': language_name,
        'kalite_languages': kalite,
        'wikifundi_languages': wikifundi,
        'aflatoun_languages': aflatoun,
        'edupi': edupi,
        'packages': [{"name": x, "status": "present"} for x in zim_install],
        'captive_portal': True,
        'has_custom_branding': has_custom_branding,
        'custom_branding_path': '/tmp',
        'admin_account': "{login}",
        'admin_password': "{pwd}",
    }

    if wifi_pwd:
        extra_vars.update({'wpa_pass': wifi_pwd})

    if admin_account is None:
        admin_account = {'login': 'admin', 'pwd': 'admin'}

    run(machine, tags, extra_vars, admin_account)
