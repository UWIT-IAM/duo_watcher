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

You'll need to be superuser to create the archive directory for the logs.  You can do that from ref or
melville:

```bash
  # As superuser on ref or melville:
  ssh ${loggerN} "mkdir /data/logs/duo; chown iamduo /data/logs/duo"
```

Then you can grab this repo from github:

```bash
  # From your workstation:
  ssh ${loggerN}
  actas - iamduo
  git clone git@github.com:UWIT-IAM/duo_watcher.git 
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install --upgrade -r requirements.txt
```

Also, if anything changes within ./rdist, do:

```bash
   # As superuser on ref:
   rm -r /rdist/common/duo_watcher
   ssh ${loggerN} '(cd ~iamduo/duo_watcher/rdist/common; tar --owner=0 --group=0 -cf - duo_watcher)' | (cd /rdist/common/; tar -xvf -)
```
