from js9 import j

# the following hack is used to import 0-access module
# without breaking current usage of it in other places
from importlib import import_module
import sys
sys.path.append(".")
zeroaccess = import_module("0-access")

TEMPLATE = """
uri = "http://localhost:5050"
port = "5050"
organization = ""
client_secret_ = ""
ssh_ip = "127.0.0.1"
ssh_port = "22"
session_timeout = 120
gateone_url = ""
"""
JSConfigBase = j.tools.configmanager.base_class_config


class ZeroAccessServer(JSConfigBase):
    def __init__(self, instance, data=None, parent=None, interactive=False, template=None):
        if not data:
            data = {}
        if not template:
            template = TEMPLATE
        JSConfigBase.__init__(self, instance=instance, data=data, parent=parent,
                              template=template, interactive=interactive)

    def start(self):
        zeroaccess.run(**self.config.data)
