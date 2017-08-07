"""
Duo_watcher: Access Duo logs
"""

import duo_client
import json
import errno
import time
import sys
import os


with open('credentials/duo.json') as fp:
    keys = json.load(fp)

# Configuration and information about objects to create.
admin_api = duo_client.Admin(
    ikey = keys['ikey'],
    skey = keys['skey'],
    host = keys['apihost']
)


class LogWatcher:
    def __init__(self, name, resource):
        self.name = name
        self.resource = resource
        self.logname = None
        self.backoff = 0
        try:
            with open(name + '/state') as fp:
                self.state = json.load(fp)
        except IOError as e:
            if e.errno == errno.ENOENT:
                self.state = {'timestamp': 0}
            else:
                print('Unable to load {file}: {msg}'.format(
                    file = os.path.realpath(name + '/state'), msg = msg))
                sys.stdout.flush()
                raise
        except Exception as msg:
            print('Unable to load {file}: {msg}'.format(
                file = os.path.realpath(name + '/state'), msg = msg))
            sys.stdout.flush()
            raise

    def fetch(self):
        try:
            params = {
                'mintime': str(self.state['timestamp'])
            }
            response = admin_api.json_api_call(
                'GET',
                '/admin/v1/logs/' + self.resource,
                params,
            )
        except RuntimeError as e:
            if e.args == ('Received 429 Too Many Requests',):
                self.backoff = 1 + 2 * self.backoff
                if self.backoff > 10:
                    print('{ts} {pid}: Backing off to {bo} on {name}'.format(
                        ts = time.strftime('%y-%m-%d %H:%M:%S'),
                        pid = os.getpid(),
                        bo = self.backoff,
                        name = self.name))
                    sys.stdout.flush()
                return False
            raise
        else:
            self.backoff = self.backoff / 2

        newRow = False
        for row in response:
            timestamp = row.get('timestamp', 0)
            if timestamp >= self.state['timestamp']:
                tm = time.localtime(timestamp)
                fname = time.strftime(self.name + '/%y%m%d', tm)
                if self.logname and self.logname != fname:
                    self.logfp.close()
                    self.logname = None
                if not self.logname:
                    self.logname = fname
                    self.logfp = open(fname, 'a')
                    print('{ts} {pid}: Advancing to {file}'.format(
                        ts = time.strftime('%y-%m-%d %H:%M:%S'),
                        pid = os.getpid(),
                        file = os.path.realpath(fname)))
                    sys.stdout.flush()
                json.dump(row, self.logfp)
                self.logfp.write('\n')
                self.state['timestamp'] = timestamp + 1
                newRow = True

        if newRow:
            self.logfp.flush()
            with open(self.name + '/state.new', 'w') as fp:
                json.dump(self.state, fp)
                fp.write('\n')
            os.rename(self.name + '/state.new', self.name + '/state')
        return newRow
