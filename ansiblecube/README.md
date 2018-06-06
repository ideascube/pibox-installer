# AnsibleCube

This is a **very distant** fork of [ideascube/ansiblecube](https://github.com/ideascube/ansiblecube/) dedicated to [pibox-installer](https://framagit.org/ideascube/pibox-installer)'s use case.

## Goal

It aims at setting-up a complete RaspberryPi box tu use as a Content-HotSpot.

This is achieved using a two steps scenario:

1. A base image is created, running this playbook with default (no-content) values using `--tags master,resize,rename,configure`
2. Content is configured by rerenning the playbook with a configuration file and `--tags configure,resize,rename,[move|download]-content`.

## Tags

* `master`: installs all non-content-specific softwares (system, `ideascube`, `kiwix-serve`).
* `resize`: resize the `/` and `/data` partitions (image should have been already resized qemu-wise).
* `rename`: reconfigure all software according to `project_name`.
* `setup`: install and prepare all softwares without enabling them.
* `reconfigure`: sets all configuration and software according to configuration.
* `move-content`: move expected content from `/data/xxx` to proper locations, according to configuration

**Notes**:

* `resize` requires a re-run of `setup` and `reconfigure` as most content and softwares lives in `/data`.

## Features

* WiFi Hot Spot (`hostapd`)
* DNS Masquerade (`dnsmasq`)
* Captive Portal
* Web & Application servers (`nginx`, `uswgi`)
* Content & Box Manager (`ideascube`)
* ZIM files (all of [kiwix](https://kiwix.org)'s library) with indexes.
* Khan-Accademy Videos (`ka-lite`)
* Aflatoun
* Wikifundi
* EduPi

## Usage

This playbook is not meant to be run standalone on any system.

Please check [make-base-image](https://framagit.org/ideascube/pibox-installer/tree/master/make-vexpress-boot) and more generally [pibox-installer](https://framagit.org/ideascube/pibox-installer) to see it in action.

## Tests

The repo is plugged in [Travis CI](https://travis-ci.org/ideascube/ansiblecube).

### Testing locally

__Setting-up test envirronment__

``` bash
sudo apt-get install libssl-dev
virtualenv ~/.virtualenv/pytest-ansible
. ~/.virtualenv/pytest-ansible/bin/activate
cd ~/dev/ansiblecube
pip install -r tests/requirements-dev.txt
```

__Running them__

``` bash
py.test
```

__Pre-push git hook__

``` sh
#!/bin/sh
${HOME}/.virtualenv/pytest-ansible/bin/py.test
```
