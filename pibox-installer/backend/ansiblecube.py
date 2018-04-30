import json

ansiblecube_path = "/var/lib/ansible/local"


def run_for_image(machine, resize):
    tags = ['master', 'configure']
    if resize:
        tags.append('resize')

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


def run_for_user(machine, name, timezone, wifi_pwd,
                 edupi, wikifundi, aflatoun, kalite, zim_install,
                 admin_account):
    extra_vars = {
        'project_name': name,
        'timezone': timezone,
        'kalite_languages': kalite,
        'wikifundi_languages': wikifundi,
        'aflatoun_languages': aflatoun,
        'edupi': edupi,
        'packages': [{"name": x, "status": "present"} for x in zim_install],
        'captive_portal': True,
    }
    if wifi_pwd:
        extra_vars.update({'wpa_pass': wifi_pwd})

    if admin_account is not None:
        extra_vars.update({'admin_account': "{login}",
                           'admin_password': "{pwd}"})

    run(machine, ['configure', 'content'], extra_vars, admin_account)


def run(machine, tags, extra_vars={}, secret_kwargs={}):
    ''' machine must provide write_file and exec_cmd functions '''

    machine.exec_cmd("sudo apt-get update")

    ansible_args = "--inventory hosts"
    ansible_args += " --tags {}".format(",".join(tags))
    ansible_args += " --extra-vars \"%s\"" % json.dumps(extra_vars)
    ansible_args += " main.yml"

    ansible_pull_cmd = (
        "sudo sh -c 'cd {} && /usr/local/bin/ansible-playbook {}'"
        .format(ansiblecube_path, ansible_args))

    if secret_kwargs:
        run_ansible_pull_cmd = ansible_pull_cmd.format(**secret_kwargs)
        displayed_ansible_pull_cmd = ansible_pull_cmd.format(
            **{k: '****' for k, v in secret_kwargs.items()})

    machine.exec_cmd(run_ansible_pull_cmd, displayed_ansible_pull_cmd)
