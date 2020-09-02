"""
Argus_daemon: A generic daemon that will respond to Argus queries and
fire off some specific subthreads to do actual work
"""

import atexit
import errno
import json
import os
import re
import socket
import signal
import sys
import time

from time import localtime, strftime
from threading import Thread, Event

getSeq = re.compile(r'(^[0-9 ]*)(.*)')
res_fmt = '{seq}P{alert}{status}\n\n{threads}'
thread_re = re.compile(r'^thread ([a-z]+) ([a-zA-Z_0-9]+)[ ]*([a-zA-Z_0-9]+)*[ ]*([a-zA-Z_0-9]+)*')

class Argus_termination(Exception):
    pass

class Argus_thread:
    """
    Defines the control mechanism for an Argus thread.

    active:    Boolean -- indicates the thread is running
    alert:     Integer -- Argus alert level for thread
    auto:      Boolean -- Auto start
    count:     Integer -- Number of cycles performed
    handle:    Nonspec -- Thread specific
    interval:  Integer -- Cycle period in seconds
    maxcount:  Integer -- Maximum number of cycles (-1 for infinite)
    name:      String  -- Thread name
    resource:  String  -- Thread specific
    status:    String  -- Thread specific status message
    target:    Module  -- Thread loop processor
    terminate: Event   -- Thread termination control
    thread:    Thread  -- Thread instance
    timestamp: time_t  -- Last cycle timestamp
    """
    def __init__(self, name, resource, target,
                 maxcount = -1,
                 interval = 90,
                 auto = True):
        self.active = False
        self.alert = 0
        self.auto = auto
        self.count = 0
        self.handle = None
        self.interval = interval
        self.maxcount = maxcount
        self.name = name
        self.resource = resource
        self.status = 'Starting'
        self.target = target
        self.terminate = Event()
        self.thread = None
        self.timestamp = time.time()


class Argus:
    """
    Instantiating the Argus class will start up the daemon and any
    auto start threads.  The main thread should then call getMessage()
    in a loop to service the Argus queries.  The argus_cf file in
    the starting directory contains the following:

    {
        'addr':     '',                     # Server source IP address
        'port':     2680,                   # Server port
        'rundir':   '/usr/tmp'              # Directory to cd to
        'logfile':  'log',                  # File for query records/issues
        'pidfile':  '/var/run/xxx.pid',     # For daemon stopping
    }
    """
    def __init__(self, threads=[]):
        """
        threads: An array of type Argus_thread
        """
        with open('argus_cf') as fp:
            cf = json.load(fp)

        pname = sys.argv[0].split('/')[-1].split('.')[0]

        self.alert = 0
        self.logfile = cf.get('logfile', pname + '.log')
        self.pidfile = cf.get('pidfile', '/var/run/' + pname + '.pid')
        self.port = cf.get('port', 2680)
        self.rundir = cf.get('rundir', '/var/tmp')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.status = 'Ready'
        self.terminate = False
        self.threads = threads

        try:
            self.sock.bind((cf.get('addr', ''), self.port))
        except socket.error as e:
            sys.stderr.write('Unable to bind to UDP port {port}: {msg}\n'.format(port = self.port, msg = e.strerror))
            sys.exit(1)

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        os.chdir(self.rundir)

        print('{ts} {pid}: Ready to accept requests on port {port}.'.format(
            ts = time.strftime('%y-%m-%d %H:%M:%S'),
            pid = os.getpid(),
            port = self.port))
        sys.stdout.flush()

    def deamonize(self):
        """
        Become a proper daemon
        """

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write('fork #1 failed: {msg}\n'.format(msg = e.strerror))
            sys.exit(1)

        os.setsid()

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write('fork #2 failed: {msg}\n'.format(msg = e.strerror))
            sys.exit(1)

        sys.stdout.flush()
        sys.stderr.flush()

        os.close(0)
        os.close(1)
        os.close(2)

        sys.stdin = open('/dev/null', 'r')
        sys.stdout = open(self.logfile, 'a+')
        sys.stderr = open(self.logfile, 'a+')

        atexit.register(self.delpid)
        pfp = open(self.pidfile, 'w+')
        pfp.write('{pid}\n'.format(pid = os.getpid()))
        pfp.close()

    def delpid(self):
        """
        Internal routine to clean up our pidfile on daemon termination
        """
        try:
            os.remove(self.pidfile)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def getMessage(self):
        """
        Our main thread should spend all its time here as part of its main loop
        """
        sys.stdout.flush()
        sys.stderr.flush()

        while not self.terminate:
            try:
                bytes, self.addr = self.sock.recvfrom(1024)
            except Argus_termination:
                continue
            except IOError as e:
                if e.errno == errno.EINTR:
                    continue
                raise

            if not bytes:
                continue

            cmd = getSeq.match(bytes.decode("utf-8"))

            self.seq = cmd.group(1)
            self.msg = cmd.group(2)

            if len(self.msg) < 1:
                continue

            # Ack commands will clear our current status

            if self.msg == 'ack' or self.msg == 'clear':
                self.alert = 0
                self.status = 'Ready'
                self.msg = 'status'

            # We'll handle status queries from anywhere...

            if self.msg[0] == 's':
                alert = self.alert
                status = self.status
                res_threads = ''
                restart = None
                for tp in self.threads:
                    if not tp.active:
                        res_threads = res_threads + '{name}: Idle\n'.format(name = tp.name)
                        continue
                    res_threads = res_threads + '{name}: {status}\n'.format(name = tp.name, status = tp.status)
                    if alert < tp.alert:
                        alert = tp.alert
                    if alert < 6:
                        if time.time() > tp.timestamp + 4 * tp.interval:
                            alert = 5
                            status = 'Dead thread: {name}'.format(name = tp.name)
                            if tp.auto:
                                alert = 6
                                restart = tp
                            else:
                                alert = 5

                response = res_fmt.format(seq = self.seq, alert = alert, status = status, threads = res_threads)
                packet = response.encode("utf-8")
                self.sock.sendto(packet, self.addr)

                # Should we attempt to auto restart a dead thread??

                if restart:
                    restart.terminate.set()
                    restart.thread.join(10.0)
                    if restart.thread.isAlive():
                        print('{ts} {pid}: Unable to terminate {name} thread.'.format(
                            ts = time.strftime('%y-%m-%d %H:%M:%S'),
                            pid = os.getpid(),
                            name = restart.name))
                        sys.stdout.flush()
                        restart.auto = False
                    else:
                        restart.active = False
                        restart.thread = None
                        restart.terminate.clear()
                        restart.count = 0
                        try:
                            restart.thread = Thread(target=restart.target, args=(restart,))
                            restart.thread.start()
                        except Exception as errtxt:
                            print('{ts} {pid}: Unable to restart {name}: {msg}'.format(
                                ts = time.strftime('%y-%m-%d %H:%M:%S'),
                                pid = os.getpid(),
                                name = restart.name,
                                msg = errtxt))
                            sys.stdout.flush()
                        else:
                            print('{ts} {pid}: Restarted {name} thread.'.format(
                                ts = time.strftime('%y-%m-%d %H:%M:%S'),
                                pid = os.getpid(),
                                name = restart.name))
                            sys.stdout.flush()
                            restart.active = True

                continue

            # Other requests need to come from our localhost.

            if self.addr[0] != '127.0.0.1':
                continue

            # We receive an 'n' to open a new log file

            if self.msg == 'newlog' or self.msg == 'rotate':
                sys.stdout.flush()
                sys.stderr.flush()

                sys.stdout.close()
                sys.stdout = open(self.logfile, 'a+')

                sys.stderr.close()
                sys.stderr = open(self.logfile, 'a+')

                fmt = ('{ts} {pid}: Continuing to accept '
                       'requests on port {port}.')
                print(fmt.format(ts = time.strftime('%y-%m-%d %H:%M:%S'), pid = os.getpid(), port = self.port))
                sys.stdout.flush()

                response = '{seq}P0Okay\n'.format(seq = self.seq)
                packet = response.encode("utf-8")
                self.sock.sendto(packet, self.addr)
                continue

            print('{ts} {pid}: Incoming {msg}'.format(ts = time.strftime('%y-%m-%d %H:%M:%S'), pid = os.getpid(), msg = self.msg))
            sys.stdout.flush()

            if self.thread_cmd():
                continue

            return self.msg

        return None

    def sendResponse(self, message):
        """
        Sends a response back to the source of the most recent query
        """
        response = '{seq}{message}\n'.format(seq = self.seq, message = message)
        packet = response.encode("utf-8")
        self.sock.sendto(packet, self.addr)
        print('{ts} {pid}: Response {msg}'.format(
            ts = time.strftime('%y-%m-%d %H:%M:%S'),
            pid = os.getpid(),
            msg = message))
        sys.stdout.flush()

    def shutdown(self, signum, frame):
        """
        Catch some otherwise fatal signals so we can shut ourselves down gracefully
        """
        print('{ts} {pid}: Shutting down on signal {signum}'.format(
            ts = time.strftime('%y-%m-%d %H:%M:%S'),
            pid = os.getpid(),
            signum = signum))
        sys.stdout.flush()

        self.terminate = True
        raise Argus_termination()

    def thread_cmd(self):
        """
        Internal routine for handling thread releated requests
        """
        m = thread_re.match(self.msg)
        if not m:
            return False

        answer = 'P5No such thread'
        for tp in self.threads:
            if m.group(1) == tp.name:
                if m.group(2) == 'terminate' or m.group(2) == 'stop':
                    tp.terminate.set()
                    tp.thread.join(10.0)
                    if tp.thread.isAlive():
                        answer = 'P5Thread {name} could not be joined'.format(name = tp.name)
                    else:
                        tp.active = False
                        tp.thread = None
                        answer = 'P2Thread {name} terminated'.format(name = tp.name)
                    break

                if m.group(2) == 'start':
                    if tp.active:
                        answer = 'P5Thread {name} is already active.'.format(name = tp.name)
                        break

                    tp.terminate.clear()
                    tp.count = 0
                    try:
                        tp.thread = Thread(target=tp.target, args=(tp,))
                        tp.thread.start()
                    except Exception as errtxt:
                        answer = 'P5Thread {name} failed: {msg}'.format(name = tp.name, msg = errtxt)
                        raise
                    else:
                        tp.active = True
                        answer = 'P2Thread {name} started'.format(name = tp.name)
                    break

                if m.group(2) == 'interval':
                    try:
                        n = int(m.group(3))
                    except Exception as errtxt:
                        answer = 'P5Thread {name} invalid interval: {msg}'.format(name = tp.name, msg = errtxt)
                        break
                    if n > 0:
                        tp.interval = n
                        answer = 'P2Thread {name} interval set to {n}'.format(name = tp.name, n = n)
                    else:
                        answer = 'P5Thread {name} invalid interval {n}'.format(name = tp.name, n = n)
                    break

                if m.group(2) == 'maxcount':
                    try:
                        n = int(m.group(3))
                    except Exception as errtext:
                        answer = 'P5Thread {name} invalid maxcount: {msg}'.format(name = tp.name, msg = errtxt)
                        break

                    tp.maxcount = n
                    answer = 'P2Thread {name} maxcount set to {n}'.format(name = tp.name, n = n)
                    break

                answer = 'P5Thread {name} invalid option'.format(name = tp.name)
                break

        self.sendResponse(answer)
        return True
