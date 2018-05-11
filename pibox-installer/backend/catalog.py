
import urllib.request
import yaml

CATALOGS = [
    {'name': "Kiwix",
     'description': "Kiwix ZIM Content",
     'url': "http://download.kiwix.org/library/ideascube.yml"},
    {'name': "StaticSites",
     'description': "Static sites",
     'url': "http://catalog.ideascube.org/static-sites.yml"}
]

YAML_CATALOGS = []
try:
    for catalog in CATALOGS:
        with urllib.request.urlopen(catalog.get('url')) as f:
            YAML_CATALOGS.append(yaml.load(f.read().decode("utf-8")))
except Exception:
    pass
