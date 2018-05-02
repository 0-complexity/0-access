from js9 import j
from .ZeroAccessServer import ZeroAccessServer

JSConfigBase = j.tools.configmanager.base_class_configs


class ZeroAccessFactory(JSConfigBase):
    def __init__(self):
        self.__jslocation__ = "j.servers.zeroaccess"
        JSConfigBase.__init__(self, ZeroAccessServer)

    def baseclass_get(self):
        return self._child_class

    def start(self, instance="main", background=False):
        server = self.get(instance, create=False, interactive=False)
        if background:
            cmd = "js9 '%s.start(instance=\"%s\")'" % (self.__jslocation__, instance)
            j.tools.tmux.execute(cmd, session='main', window='zeroaccess_%s' % instance,
                                 pane='main', session_reset=False, window_reset=True)
            res = j.sal.nettools.waitConnectionTest("localhost", int(server.config.data["port"]), timeoutTotal=1000)
            if not res:
                raise RuntimeError("Could not start ZeroAccess server on port:%s" % int(server.config.data["port"]))
            self.logger.info("ZeroAccess server '%s' started" % instance)
        else:
            server.start()

    def configure(self, instance, port, uri, organization, client_secret,
                  ssh_ip, ssh_port, session_timeout, gateone_url="", interactive=False):
        data = {
            "uri": uri,
            "port": port,
            "organization": organization,
            "client_secret_": client_secret,
            "ssh_ip": ssh_ip,
            "ssh_port": ssh_port,
            "session_timeout": session_timeout,
            "gateone_url": gateone_url
        }
        self._child_class(instance=instance, data=data, parent=self, interactive=interactive)
        return
