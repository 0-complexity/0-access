#!/usr/bin/python3
#
# Web server that authenticates people via itsyou.online and provides ssh access via web
# SSH sessions are recorded automatically, and uploaded to a remote site for playback
#

from gevent import monkey, spawn_later, sleep
monkey.patch_socket()
monkey.patch_ssl()
from gevent.wsgi import WSGIServer

import flask
import os
import uuid
import time
import signal
import re
import json
import psutil
import math
import index
from flask import Flask, request, render_template, session, redirect, jsonify, request
from flask_itsyouonline import ItsyouonlineProvider
from js9 import j

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()


SESSION_INIT_TIME = 20
SESSION_POLL_TIME = 5
SESSION_WARN_TIME = 10
IP_MATCH = re.compile("^([0-9]{1,3}\.){3}[0-9]{1,3}$")


app = flask.Flask(__name__)
app.secret_key = os.urandom(24)


def run(args):
    config = {
        'ROOT_URI': args.uri,
        'CLIENT_ID': args.client_id,
        'CLIENT_SECRET': args.client_secret,
        'REDIRECT_URI': "%s/callback" % args.uri,
        'SCOPE': 'user:publickey:ssh',
        'ORGANIZATION': args.organization,
        'AUTH_ENDPOINT': '/',
        'CALLBACK_ENDPOINT': '/callback',
        'ON_COMPLETE_ENDPOINT': '/ssh/',
        'SSH_IP': args.ssh_ip,
        'SSH_PORT': args.ssh_port,
        'SSH_SESSION_TIME_OUT': args.session_timeout
    }
    app.config.update(config)
    itsapp = ItsyouonlineProvider()
    itsapp.init_app(app)
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


@app.route("/ssh/", methods=["GET"])
@app.route("/ssh/<remote>", methods=["GET"])
def ssh(remote=None):
    if remote and not IP_MATCH.match(remote):
        return 'Bad remote', 400
    if not 'iyo_user_info' in session:
        session['remote'] = remote
        return redirect("/")
    if not remote and session.get('remote'):
        return redirect("/ssh/%s" % session.get('remote'))
    if not remote:
        return 'Remote not set', 400
    return render_template('0-access.html', remote=remote)


@app.route("/provision/<remote>", methods=["POST"])
def provision(remote):
    if not IP_MATCH.match(remote):
        return 'Bad remote', 400
    if not 'iyo_user_info' in session:
        return redirect("/")

    provisioned = session.get("provisioned")
    if provisioned:
        return jsonify(provisioned)

    iyo_user_info = session["iyo_user_info"]
    start = time.time()
    username = str(uuid.uuid4()).replace("-", "")
    home = "/home/%s" % username
    j.tools.prefab.local.system.user.create(username, home=home, shell="/bin/lash")
    for key in iyo_user_info["publicKeys"]:
        j.tools.prefab.local.system.ssh.authorize(username, key["publickey"])

    j.sal.fs.copyFile("/root/.ssh/id_rsa", "/home/%s/.ssh" % username)
    j.sal.fs.chown("/home/%s/.ssh" % username, username, username)
    j.sal.fs.writeFile("/home/%s/.remote" % username, "REMOTE=%s" % remote)
    provisioned = dict(username=username, ssh_ip=app.config['SSH_IP'], ssh_port=app.config['SSH_PORT'])

    ssh_session = Session(username=username)
    ssh_session.iyo_username = iyo_user_info['username']
    ssh_session.iyo_firstname = iyo_user_info['firstname']
    ssh_session.iyo_lastname = iyo_user_info['lastname']
    ssh_session.iyo = json.dumps(iyo_user_info, ensure_ascii=False)
    ssh_session.remote = remote
    db = app.config["db"]()
    db.add(ssh_session)
    db.commit()    


    def kill_session():
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
        db.commit()
        idx = app.config["idx"]
        idx.index(username, ssh_session.start, ssh_session.end, iyo_user_info['username'], remote)
        j.tools.prefab.local.system.user.remove(username, rmhome=True)


    def monitor():
        stop = False
        try:
            exit_code, stdout, stderr = j.tools.prefab.local.core.run("who")
            if exit_code != 0:
                app.logger.error('Failed to list ttys\n%s' % stderr)
                return
            lines = [line for line in stdout.splitlines() if username in line]
            app.logger.info('User %s %s has %s ssh sessions!' % (iyo_user_info['firstname'], iyo_user_info['lastname'], len(lines)))
            if len(lines) == 0:
                kill_session()
                stop = True
                return
            now = int(time.time())
            if now > start + app.config["SSH_SESSION_TIME_OUT"]:
                kill_session()
                stop = True
            elif now > start + app.config["SSH_SESSION_TIME_OUT"] - SESSION_WARN_TIME:
                for line in lines:
                    parts = [s for s in line.split(" ") if s]
                    with open("/dev/%s" % parts[1], 'w') as f:
                        f.write("Warning: this ssh session will be closed within %s seconds\r\n" % (start + app.config['SSH_SESSION_TIME_OUT'] - now))
        finally:
            if not stop:
                spawn_later(SESSION_POLL_TIME, monitor)
    spawn_later(SESSION_INIT_TIME, monitor)
    return jsonify(provisioned)


@app.route("/sessions")
def sessions():
    db = app.config["db"]()
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
            base_query = db.query(Session).filter(Session.iyo_username==user)
        else:
            base_query = db.query(Session)
        if remote:
            base_query = base_query.filter(Session.remote==remote)
        page_count = math.ceil(base_query.count()/10)
        sessions = list()
        result = dict(page=dict(href="%s/sessions?page=%s" % (app.config["ROOT_URI"], page), sessions=sessions), total_pages=page_count)
        for ssh_session in base_query.order_by(Session.start.desc())[(page-1)*10:page*10]:
            end = ssh_session.end.timestamp() if ssh_session.end else None
            sessions.append(dict(user=dict(href="%s/sessions?user=%s" % (app.config['ROOT_URI'], ssh_session.iyo_username), username=ssh_session.iyo_username, firstname=ssh_session.iyo_firstname, lastname=ssh_session.iyo_lastname), 
                                start=ssh_session.start.timestamp(),
                                end=end,
                                remote=ssh_session.remote,
                                href="%s/sessions/%s" % (app.config['ROOT_URI'], ssh_session.username)))
    return jsonify(result)


@app.route("/sessions/<session_id>")
def session_download(session_id):
    db = app.config["db"]()
    if db.query(Session).filter(Session.username==session_id).count() != 1:
        return "Session not found!", 404
    filename = "/var/recordings/%s.json" % session_id
    if not j.sal.fs.exists(filename):
        return "Session recording not found!", 404
    return j.sal.fs.readFile(filename)


class Session(Base):
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
    parser = argparse.ArgumentParser(description='0-access server')
    parser.add_argument('client_id', type=str, help='Itsyou.Online client id')
    parser.add_argument('client_secret', type=str, help='Itsyou.Online client secret')
    parser.add_argument('organization', type=str, help='Itsyou.Online organization')
    parser.add_argument('uri', type=str, help='uri, Eg http://localhost:4000')
    parser.add_argument('port', type=int, help='Port to listen for connections')
    parser.add_argument('ssh_ip', type=str, help='Ip address for the ssh server')
    parser.add_argument('ssh_port', type=int, help='Port for the ssh server')
    parser.add_argument('session_timeout', type=int, help='Time when session will timeout, and be killed')
    args = parser.parse_args()
    run(args)