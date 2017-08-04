#!/usr/local/bin/python2.6
"""
Collect: Collect Duo logs
"""

import argparse
import re
import time
import traceback
from threading import Thread, Event
from time import localtime, strftime

import argus_daemon
import duo_watcher


def looper(tp):
    """
    Thread to loop forever scarfing up Duo log messages, yum, yum
    """
    while not tp.terminate.isSet():
        while not tp.terminate.isSet():
            tp.timestamp = time.time()
            result = tp.handle.fetch()
            tp.count = tp.count + 1
            t0 = strftime('%H:%M:%S', localtime(tp.timestamp))
            t1 = strftime('%y-%m-%d %H:%M:%S', localtime(tp.handle.state['timestamp']))
            tp.status = 'At {wall} up to {log} count: {count} interval: {val}'.format(wall=t0, log=t1, count=tp.count, val=tp.interval)
            if tp.handle.backoff > 0:
                tp.status = tp.status + '+{bo}'.format(bo=tp.handle.backoff)
            if not result:
                break
        tp.terminate.wait(tp.interval + tp.handle.backoff)
        if tp.maxcount > 0 and tp.count > tp.maxcount:
            break
    tp.status = 'Stopped ' + tp.status
    print('Thread for {name} terminating...'.format(name = tp.name))

#
#  Initialize our thread descriptions
#

threads = [
    argus_daemon.Argus_thread('auth', 'authentication', auto = False, target = looper),
    argus_daemon.Argus_thread('admin', 'administrator', auto = False, target = looper),
    argus_daemon.Argus_thread('phone', 'telephony', auto = False, target = looper)
]

#
#  Start the Argus listener and become a proper daemon
#

argus = argus_daemon.Argus(threads)


def main():
    ap = argparse.ArgumentParser(description='Collect Duo Logs')
    ap.add_argument('-d', action='store_true', help='Become a deamon')
    arg = ap.parse_args()

    if arg.d:
        argus.deamonize()

    for tp in threads:
        tp.handle = duo_watcher.LogWatcher(tp.name, tp.resource)
        if tp.auto:
            try:
                tp.thread = Thread(target=looper, args=(tp,))
                tp.thread.start()
            except Exception as errtxt:
                tp.alert = 8
                tp.status = '{msg}'.format(msg=errtxt)
            else:
                tp.active = True

    #
    #  Enter the main loop
    #

    while True:
        try:
            line = argus.getMessage()
        except KeyboardInterrupt:
            print('')
            break
        except:
            print('Exiting loop because of unhandled exception')
            traceback.print_exc()
            break

        if not line:
            break

        answer = 'P5Unrecognized command'

        if line == 'help':
            answer = ('P3Help yourself\n\n' +
                      'Commands are:\n' +
                      '  clear: Clear status\n' +
                      '  status: Report status\n' +
                      '  rotate: Logfile rotation\n' +
                      '  thread {name} start\n' +
                      '  thread {name} stop\n' +
                      '  thread {name} interval {seconds}\n' +
                      '  thread {name} maxcount {count}\n' +
                      'Threads are:\n')

            for tp in threads:
                answer = answer + '  {name}: Duo {resource} log watcher\n'.format(name = tp.name, resource = tp.resource)

        argus.sendResponse(answer)

    #
    #  Clean up after termination
    #

    print('Exiting main loop.')

    for tp in threads:
        if tp.active:
            tp.terminate.set()

    for tp in threads:
        if tp.active:
            print('Joining thread for {name}'.format(name = tp.name))
            tp.thread.join(10.0)
        tp.active = False
        tp.thread = None


if __name__ == '__main__':
    main()
