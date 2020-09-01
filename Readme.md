# Duo Watcher

The Duo watcher package contains a daemon that continually collects the tail end of the Duo logs
and archives them on the local server for later perusal.  This process is intended to run as user
iamduo on the loggerN system and collect the logs under the /data/logs/duo directory.


## Installation

We don't have an automated procedure for pushing stuff directly to loggerN.  Instead we'll assume iamduo's
identity, grab the repo and set it up.  The iamduo account on logger4 had, at one point, the ability to
grab this repo.  If you're working with logger5 or logger6 you'll want to grab some junk from iamduo's
home directory on logger4 and copy it to the iamduo account on your new system.  In particular, the
.bashrc and the contents of the bin and .ssh directories.

If you want to copy-paste directly from this Readme file:

```bash
  # On your workstation, in your root ref and/or melville sessions:
  export loggerN=logger4
  export loggerX=logger3
```

You can grab this repo from github:

```bash
  ssh ${loggerN}
  actas - iamduo
  git clone git@github.com:UWIT-IAM/duo_watcher.git
  cd ~/duo_watcher
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install --upgrade -r requirements.txt
```

By hook or by crook you'll need to manufacture the Duo credentials:

```bash
  ssh ${loggerN}
  actas - iamduo
  cd ~/duo_watcher
  mkdir -p ./credentials
  cp ${SOURCE_FILE} ./credentials/duo.json
```

If anything changed within ./rdist, double check it wasn't anything nasty, and do:

```bash
   # As superuser on ref:
   rm -r /rdist/common/duo_watcher
   ssh ${loggerN} '(cd ~iamduo/duo_watcher/rdist/common; tar --owner=0 --group=0 -cf - duo_watcher)' | (cd /rdist/common/; tar -xvf -)

   # Install with:
   clone ${loggerN} update

   # Or, iff ~ken/.bin/ is in your path:
   push /rdist/common/duo_watcher/ ${loggerN} | sh
```

You'll need to be superuser to create the archive directory for the logs.  You can do that from ref or
melville:

```bash
  # As superuser on ref or melville:
  ssh ${loggerN} "mkdir /data/logs/duo; chown iamduo /data/logs/duo"
```

If you can copy the files from the /data/logs/duo/{admin,auth,phone} directories on
the previous loggerX system, # including the "state" file, you should do that now.

```bash
  # As superuser on ref or melville:
  day=`date +%d`
  if [ $day -gt 15 ]; then
    list="15 45 75 105 135 165 195 225 255 285 315 345"
  else
    list="0 30 60 90 120 150 180 210 240 270 300 330"
  fi
  for dir in admin auth phone; do
    files=${dir}/state\ `for x in $list; do date -d "$x days ago" "+${dir}/%y%m*"; done|fmt -1000`
    ssh ${loggerX} "cd /data/logs/duo && tar -cf - $files" |
	ssh ${loggerN} "cd /data/logs/duo && tar -xvf -"
  done
```

Now you can start the daemon up to pick up where loggerX left off:

```bash
  # As superuser on ref or melville:
  ssh ${loggerN} "service duo_watcher start"
```

## Maintenance

Once the duo_watcher service is running and loggerN is declared a "production" server, the
submon monitor should keep an eye on it.

Each of the three Duo logs, `auth`, `admin` and `phone`, are collected and stored in their
own directory under the /data/logs/duo umbrella.  A new log file will be started each day
and will include all the messages received from the Duo server, each line being a JSON object.

A state file lives with the log files.  The duo_watcher daemon uses this state file to
determine how far it had gotten in fetching that log so it can pick up where it left off
the next time it starts up.  The state file records the timestamp of the last message
received plus the count of the number of times that timestamp has appeared in the log.

### Argus queries

Anybody can send the duo_watcher a "status" ding:

```bash
  # Wherever:
  ding ${loggerN} 2681 s

  Sent message 's' to 127.0.0.1 (2681).
  Recv message from   127.0.0.1 (2681) len=203.
  Got: P0Ready
     
     auth: At 20:54:43 up to 20-08-31 20:52:32 count: 2 interval: 90
     admin: At 20:54:42 up to 20-08-31 18:46:57 count: 1 interval: 90
     phone: At 20:54:42 up to 20-08-31 20:54:03 count: 1 interval: 90
```

From loggerN itself, you can send it more interesting commands to control the
individual threads:

```bash
  # From a loggerN shell:
  ding localhost 2681
  Mess: help
  Sent message 'help' to 127.0.0.1 (2681).
  Recv message from   127.0.0.1 (2681) len=342.
  Got: P3Help yourself
     
     Commands are:
       clear: Clear status
       status: Report status
       rotate: Logfile rotation
       thread {name} start
       thread {name} stop
       thread {name} interval {seconds}
       thread {name} maxcount {count}
     Threads are:
       auth: Duo authentication log watcher
       admin: Duo administrator log watcher
       phone: Duo telephony log watcher
     
  Mess: 
```

### Clean up

A cron job in /etc/cron.d/duo_watcher will eliminate log files that are more
than a year old.

