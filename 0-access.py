#!/usr/bin/python3
#
# Web server that authenticates people via itsyou.online and provides ssh access via web
# SSH sessions are recorded automatically, and uploaded to a remote site for playback
#


from gevent import monkey, sleep, spawn_later
from gevent.wsgi import WSGIServer
monkey.patch_socket()
monkey.patch_ssl()

# pylint: disable=C0411,C0413
import json
import math
import os
import re
import time
import uuid

import flask
from flask import jsonify, render_template, request, session

import index
import psutil
from flask_itsyouonline import authenticated, configure
from js9 import j
from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base() # pylint: disable=C0103


SESSION_INIT_TIME = 120
SESSION_POLL_TIME = 5
SESSION_WARN_TIME = 300
IP_MATCH = re.compile("^([0-9]{1,3}\.){3}[0-9]{1,3}$") # pylint: disable=W1401


app = flask.Flask(__name__)  # pylint: disable=C0103
app.secret_key = os.urandom(24)


def run(args):
    """
    Main entry function
    """

    config = {
        'ROOT_URI': args.uri,
        'CLIENT_SECRET': args.client_secret,
        'SSH_IP': args.ssh_ip,
        'SSH_PORT': args.ssh_port,
        'SSH_SESSION_TIME_OUT': args.session_timeout
    }
    app.config.update(config)

    configure(app, args.organization, args.client_secret, "%s/callback" % args.uri,
              '/callback', 'user:publickey:ssh')

    if not j.tools.prefab.local.system.process.find("sshd"):
        j.tools.prefab.local.core.run("/usr/sbin/sshd")
    from sqlalchemy import create_engine
    engine = create_engine('sqlite:///0-access.sqlite')

    from sqlalchemy.orm import sessionmaker
    db_session = sessionmaker()
    db_session.configure(bind=engine)
    app.config["db"] = db_session
    Base.metadata.create_all(engine)
    idx = index.Indexor()
    app.config["idx"] = idx
    WSGIServer(("0.0.0.0", args.port), app.wsgi_app).serve_forever()


@app.route("/", methods=["GET"])
@authenticated
def root():
    """
    Root url handler
    """
    return render_template('root.html')


@app.route("/ssh/<remote>", methods=["GET"])
@authenticated
def ssh(remote):
    """
    Ssh session handler
    """
    if not IP_MATCH.match(remote):
        return 'Bad remote', 400
    return render_template('0-access.html', remote=remote)


@app.route("/provision/<remote>", methods=["GET", "POST"])
@authenticated
def provision(remote):
    """
    Ssh session provisioning handler
    """
    if not IP_MATCH.match(remote):
        return 'Bad remote %s' % remote, 400

    iyo_user_info = session["iyo_user_info"]
    start = int(time.time())
    username = str(uuid.uuid4()).replace("-", "")
    home = "/home/%s" % username
    j.tools.prefab.local.system.user.create(username, home=home, shell="/bin/lash")
    settings = dict(command="/bin/lash")
    settings["no-agent-forwarding"] = True
    settings["no-port-forwarding"] = True
    settings["no-user-rc"] = True
    settings["no-x11-forwarding"] = True
    for key in iyo_user_info["publicKeys"]:
        j.tools.prefab.local.system.ssh.authorize(username, key["publickey"], **settings)

    j.sal.fs.copyFile("/root/.ssh/id_rsa", "/home/%s/.ssh" % username)
    j.sal.fs.chown("/home/%s/.ssh" % username, username, username)
    j.sal.fs.writeFile("/home/%s/.remote" % username, "REMOTE=%s" % remote)
    provisioned = dict(username=username, ssh_ip=app.config['SSH_IP'],
                       ssh_port=app.config['SSH_PORT'],
                       warned=False)

    ssh_session = Session(username=username)
    ssh_session.iyo_username = iyo_user_info['username']
    ssh_session.iyo_firstname = iyo_user_info['firstname']
    ssh_session.iyo_lastname = iyo_user_info['lastname']
    ssh_session.iyo = json.dumps(iyo_user_info, ensure_ascii=False)
    ssh_session.remote = remote
    database = app.config["db"]()
    database.add(ssh_session)
    database.commit()


    def _kill_session():
        j.sal.fs.chown("/home/%s/.ssh" % username, "root", "root")
        while True:
            for p in psutil.process_iter():
                if p.username() == username and p.name() == "ssh":
                    p.terminate()
                    sleep(5)
                    if p.is_running():
                        p.kill()
                    break
            else:
                break
        while True:
            for p in psutil.process_iter():
                if p.username() == username and p.name() == "asciinema":
                    sleep(5)
                    break
            else:
                break
        ssh_session.end = func.now()
        database.commit()
        idx = app.config["idx"]
        idx.index(username, ssh_session.start, ssh_session.end, iyo_user_info['username'], remote)
        j.tools.prefab.local.system.user.remove(username, rmhome=True)


    def _monitor():
        stop = False
        try:
            exit_code, stdout, stderr = j.tools.prefab.local.core.run("who")
            if exit_code != 0:
                app.logger.error('Failed to list ttys\n%s', stderr)
                return
            lines = [line for line in stdout.splitlines() if username in line]
            app.logger.info('User %s %s has %s ssh sessions!', iyo_user_info['firstname'],
                            iyo_user_info['lastname'], len(lines))
            if not lines:
                _kill_session()
                stop = True
                return
            now = int(time.time())
            if now > (start + app.config["SSH_SESSION_TIME_OUT"]):
                _kill_session()
                stop = True
            elif not provisioned["warned"] and now > (start + app.config["SSH_SESSION_TIME_OUT"]
                                                      - SESSION_WARN_TIME):
                for line in lines:
                    parts = [s for s in line.split(" ") if s]
                    with open("/dev/%s" % parts[1], 'w') as f:
                        f.write("Warning: this ssh session will be closed within %s seconds\r\n"
                                % (start + app.config['SSH_SESSION_TIME_OUT'] - now))
                provisioned["warned"] = True
        finally:
            if not stop:
                spawn_later(SESSION_POLL_TIME, _monitor)
    spawn_later(SESSION_INIT_TIME, _monitor)
    return jsonify(provisioned)


@app.route("/sessions")
@authenticated
def sessions():
    """
    List sessions
    """
    database = app.config["db"]()
    page = request.args.get('page')
    user = request.args.get('user')
    remote = request.args.get('remote')
    query = request.args.get('query')
    if page:
        try:
            page = int(page)
        except ValueError:
            return 'Page must be an integer >= 1', 400
        if page <= 0:
            return 'Page must be an integer >= 1', 400
    else:
        page = 1
    if query:
        return jsonify(app.config['idx'].search(query, page, user, remote))
    else:
        if user:
            base_query = database.query(Session).filter(Session.iyo_username == user)
        else:
            base_query = database.query(Session)
        if remote:
            base_query = base_query.filter(Session.remote == remote)
        page_count = math.ceil(base_query.count()/10)
        sessionz = list()
        result = dict(page=dict(href="%s/sessions?page=%s" % (app.config["ROOT_URI"], page),
                                sessions=sessionz),
                      total_pages=page_count)
        for ssh_session in base_query.order_by(Session.start.desc())[(page-1)*10:page*10]:
            end = ssh_session.end.timestamp() if ssh_session.end else None
            sessionz.append(dict(user=dict(href="%s/sessions?user=%s" % (app.config['ROOT_URI'],
                                                                         ssh_session.iyo_username),
                                           username=ssh_session.iyo_username,
                                           firstname=ssh_session.iyo_firstname,
                                           lastname=ssh_session.iyo_lastname),
                                 start=ssh_session.start.timestamp(),
                                 end=end,
                                 remote=ssh_session.remote,
                                 href="%s/sessions/%s" % (app.config['ROOT_URI'],
                                                          ssh_session.username)))
    return jsonify(result)


@app.route("/sessions/<session_id>")
@authenticated
def session_download(session_id):
    """
    Download sessions
    """
    database = app.config["db"]()
    if database.query(Session).filter(Session.username == session_id).count() != 1:
        return "Session not found!", 404
    filename = "/var/recordings/%s.json" % session_id
    if not j.sal.fs.exists(filename):
        return "Session recording not found!", 404
    return j.sal.fs.readFile(filename)


@app.route("/server/config")                                                                                                                                                                       
@authenticated                                                                                                                                                                                     
def get_session_init_time():                                                                                                                                                                       
    """                                                                                                                                                                                            
    GET session init time                                                                                                                                                                          
    """                                                                                                                                                                                            
    return jsonify({'session_init_time': SESSION_INIT_TIME})

class Session(Base):
    """
    Session table
    """
    __tablename__ = 'session'
    username = Column(String, primary_key=True)
    iyo_username = Column(String)
    iyo_firstname = Column(String)
    iyo_lastname = Column(String)
    iyo = Column(String)
    start = Column(DateTime, default=func.now())
    end = Column(DateTime)
    remote = Column(String)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='0-access server') # pylint: disable=C0103
    parser.add_argument('organization', type=str, help='Itsyou.Online organization')
    parser.add_argument('client_secret', type=str, help='Itsyou.Online client secret')
    parser.add_argument('uri', type=str, help='uri, Eg http://localhost:4000')
    parser.add_argument('port', type=int, help='Port to listen for connections')
    parser.add_argument('ssh_ip', type=str, help='Ip address for the ssh server')
    parser.add_argument('ssh_port', type=int, help='Port for the ssh server')
    parser.add_argument('session_timeout', type=int,
                        help='Time when session will timeout, and be killed')
    run(parser.parse_args())
