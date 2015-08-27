## EC2 Manager Scripts

Allows control over the entire AWS, Matterhorn, Zadara stack.  These scripts 
are able to start and stop entire clusters, as well as manage the number of 
workers, and the overall maintenance state of the Matterhorn instances.  

### Getting started

1. Git clone this repo and cd into it.
1. Create a virtual environement: `virtualenv venv && source venv/bin/activate` (optional but recommended)
1. Install the requirements: `pip install -r requirements.txt`
1. Check that tests pass: `python runtests.py` (optional)
1. Create a `.env` file: `cp .env.dist .env`. See **Settings** below for required values.

### Usage

        Usage: ec2_manager.py [OPTIONS] CLUSTER COMMAND1 [ARGS]... [COMMAND2
                              [ARGS]...]...
        
        Options:
          -v, --verbose / -q, --quiet
          -d, --debug
          -n, --dry_run
          -f, --force
          --version                    Show the version and exit.
          --help                       Show this message and exit.
        
        Commands:
          autoscale    Autoscale a cluster to the correct number of...
          maintenance  Enable/disable maintenance mode on a cluster
          scale        Incrementally scale a cluster up/down a...
          scale_to     Scale a cluster to a specified number of...
          start        Start a cluster
          status       Output service job/queue status of a cluster
          stop         Stop a cluster

### General Options

* *-v/--verbose* - sends all logging output to stdout. On by default.
* *-q/--quiet* - turn off the `--verbose` behavior
* *-d/--debug* - adds more detailed logging output
* *-n/--dry_run* - the script will go through the motions but not actually change anything
* *-f/--force* - ignore some settings and wait timeouts (see more below)

All commands are actually subcommands of the main `ec2_manager.py` program,
and many take their own arguments and options. The structure
of the commands is somewhat restrictive in that the general options
listed above must always come first followed by the name/prefix
of the cluster, then the actual command and it's arguments and options.

For example, you must do this:

`./ec2-manager.py -v -d dev99 start --workers 3`

This will not work:

`./ec2-manager.py dev99 start -v -d --workers 3`

(If you're curious about the internals, take a gander at the 
[Click](http://click.pocoo.org/) framework being used. There's 
a lot to like about it, but also downside in that it's very strict 
and opinionated about how to build multi-level command interfaces.)

### Subcommands

#### status

Get a json dump of the cluster's status summary. Note that the 
`--format table` option isn't implemented yet.

    Usage: ec2_manager.py [OPTIONS] cluster status [OPTIONS]
    
      Output service job/queue status of a cluster
    
    Options:
      -f, --format [json|table]
      --help                     Show this message and exit.

#### start

Starts a cluster, including any associated Zadara arrays. 
Allows starting with a specified number of workers (default = 4).

    Usage: ec2_manager.py [OPTIONS] cluster start [OPTIONS]
    
      Start a cluster
    
    Options:
      -w, --workers INTEGER
      --help  
      
#### stop

Stop a cluster, including any associated Zadara arrays.

    Usage: ec2_manager.py [OPTIONS] cluster stop [OPTIONS]
    
      Stop a cluster
    
    Options:
      --help  Show this message and exit.

#### autoscale

Start or stop workers based on the status of queued jobs / idleness.

    Usage: ec2_manager.py [OPTIONS] cluster autoscale [OPTIONS]
    
      Autoscale a cluster to the correct number of workers based on currently
      queued jobs
    
    Options:
      --help  Show this message and exit.

#### scale

Turn on/off a specified number of workers. `DIRECTION` can be
`up` or `down`. By default starts/stops 1 worker.

    Usage: ec2_manager.py [OPTIONS] cluster scale [OPTIONS] DIRECTION
    
      Incrementally scale a cluster up/down a specified number of workers
    
    Options:
      -w, --workers INTEGER
      --help                 Show this message and exit.


#### maintenance

Enable or disable maintenance on a cluster. `STATE` can be `on` or `off'.

    Usage: ec2_manager.py [OPTIONS] cluster maintenance [OPTIONS] STATE
    
      Enable/disable maintenance mode on a cluster
    
    Options:
      --help  Show this message and exit.

#### scale_to

Intended for time-based scaling where you want to scale up/down to a specific number of workers.

    Usage: ec2_manager.py [OPTIONS] cluster scale_to [OPTIONS] WORKERS
    
      Scale a cluster to a specified number of workers
    
    Options:
      --help  Show this message and exit.


### Settings & the .env file

The program reads several configuration settings from the 
`settings.py` file, which in turn pulls any sensitive (secret) values
from environment variables. The easiest way to get those 
variables into the environment is via a `.env` file. 

Copy the provided `.env.dist` file to `.env` and edit.

#### Required

* `MATTERHORN_ADMIN_SERVER_USER`
* `MATTERHORN_ADMIN_SERVER_PASS`
* `AWS_ACCESS_KEY_ID`
* `AWS_SECRET_ACCESS_KEY`

#### Optional

* `LOGGLY_TOKEN` - send log events to loggly
* `ZADARA_ACCOUNT_TOKEN` - for controlling an associated Zadara array

#### Other settings of note

* `DEFAULT_RETRIES` - how many times the program should loop waiting for a desired state
* `DEFAULT_WAIT` - how long to sleep between retries
* `MIN_WORKERS` - minimum number of worker nodes to employ
* `MAX_WORKERS` - maximum number of worker nodes to employ
* `MIN_IDLE_WORKERS` - minimum number of idle workers to maintain
* `MAX_QUEUED_JOBS` - maximum number of queued jobs to allow for auto-scaling calculations
* `MAJOR_LOAD_OPERATION_TYPES` - the types ("id" values) of workflow operations whose jobs we want to consider when calculating autoscaling

### The --force option

The `--force` option is currently only applicable to the `stop` 
and `scale` commands. It has two effects:

1. In the case of the `scale` command, the following settings 
will be ignored: `MIN_WORKERS`, `MAX_WORKERS`, 
`MIN_IDLE_WORKERS`. 

2. For both `stop` and `scale`, it prevents the process from 
halting execution after giving up waiting for something 
to happen. For example, when stopping a cluster the process
will normally wait for some amount of time for worker nodes
to become idle, then give up, raise an exception and quit. With
`--force` enabled a warning will be logged but the process will
continue.

### Held instances

Clusters where one or more nodes have been tagged with 'hold' as a tag (the value does not
matter) are excluded from shutdown commands to allow developers to automatically 
hold clusters open.

### `autoscale` details

#### Logic

The `autoscale` command is a simplified horizontal scaling mechanism. It examines
the state of the cluster and then, based on that info decides whether to start or
stop an instance. If it sees that there are "idle" workers, i.e., worker nodes that
have no running jobs, it will attempt to stop 1 instance. If it sees that there
are "high load" jobs in the queue it will attempt to start 1 instance. It is intended
to be run as a cron job with a frequency of 2-5 minutes.
      
#### Disabling

The autoscale command checks for the presence of an 
ec2 instance tag, `autoscale`. If present with a value of "off" the autoscale 
command will exit without performing any actions.

#### Billing considerations

When an ec2 instance is started it is billed for 1 hour of usage, regardless of how
much of that hour it is actually running. Therefore, it is potentially costly to
be "flapping" instances up and down on a minute-by-minute basis. To avoid this, 
once the `autoscale` process has identified idle workers, it then looks at how 
long the instances have been "up" and rejects those whose uptime calculations 
indicate the instance has not used the bulk of it's billed hour. The threshold 
of what constitutes "the bulk of it's billed hour" is defined by 
`settings.IDLE_INSTANCE_UPTIME_THRESHOLD` (currently 50 mintues). For example, 
if an instance is seen to have only been up for 40 minutes (or 1:40, 3:33, etc.) 
it will not be shut down even if idle. If it has been up for 53 minutes (or 1:53, 
5:53, etc.) it will be shut down.

### Zadara arrays

Control of Zadara arrays is currently disabled.

### Logging

Logs are written to the `./logs` directory and logfiles are named
according to the cluster prefix being operated on. The logging
mechanism uses a `TimedRotatingFileHandler` and rotates the
log files on a daily basis.

#### Loggly

If the `LOGGLY_TOKEN` setting is available the program will
add an additional log output handler to send events to loggly. 
Events will can be identified by both the 'ec2-manager' tag and
a tag corresponding to the cluster prefix.

#### Before/After status events

Prior to and just after each command is executed a log event
will be emitted containing a summary of the cluster status, including
number of instances, workers, workers online, etc.

### Cluster naming conventions / assumptions

The following assumptions are made about how ec2 instances 
are named. 

* The instance name value will be stored in the tag 'Name'
* The instance names will all be prefixed with the name of the cluster.
e.g., all instance names in the `prdAWS` cluster will begin with `prdAWS-`
* A cluster will have one admin instance named `[prefix]-admin`
* Worker nodes will be named `[prefix]-worker`
* Engage nodes will be named `[prefix]-engage`
* DB nodes will be named `[prefix]-db`
* NFS nodes will be named `[prefix]-nfs`

These assumptions hold only for the standard ec2
Matterhorn clusters; opsworks clusters will use a different
naming scheme and controlling them will be implemented in a 
future release.
