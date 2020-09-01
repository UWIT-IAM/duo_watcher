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

```bash
  # Now you can start up the daemon to pick up where loggerX left off
  ssh ${loggerN} "service duo_watcher start"
```

