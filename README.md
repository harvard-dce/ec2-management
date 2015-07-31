EC2 Manager Scripts
===================

Allows control over the entire AWS, Matterhorn, Zadara stack.  These scripts 
are able to start and stop entire clusters, as well as manage the number of 
workers, and the overall maintenance state of the Matterhorn instances.  Clusters
where one or more nodes have been tagged with 'hold' as a tag (the value does not
matter) are excluded from shutdown commands to allow developers to automatically 
hold clusters open.

Usage
------------

usage: ec2_manager.py [-h] [-n NAME] [-c COMMAND] [-s STATE] [-m MAINTENANCE] [-w WORKERS] [-d]

### Mandatory Arguments

One of 

| Argument | Description                                                                         | Examples              |
|----------|-------------------------------------------------------------------------------------|-----------------------|
| -n       | Set the prefix of the cluster to work with.This is based on the AWS instance names. | prdAWS, devAWS, dev05 |

### Optional Arguments

| Argument | Description | Example Options  |
|----------|---------------------------------------------------------|------------------|
| -c       | The command to execute on against the specified cluster | start, stop      |
| -s       | Filters the nodes found by their AWS state, useful with -m | running, stopped |
| -m       | Sets the maintenance state on, or off | on, off          |
| -w       | Sets the desired number of workers for a cluster.  Can be combined with -c when starting up to only start a given number of workers.  Does not create new workers for you. | 0 to N           |
| -d       | Dryrun.  Does not change anything, although this will also likely not succeed.  Useful to determine which AWS nodes a given cluster name (-n) up. |                  |


### Examples

        ec2_manager.py -n dev04 -c start

Starts dev04 from a cold state.  This will not hurt anything if dev04 is already running, but it will take all of the Matterhorn nodes out of maintenance mode!  Starts the Zadara array (if applicable), then the AWS nodes, then takes Matterhorn out of maintenance.

        ec2_manager.py -n dev04 -c start -w 0

Starts all of dev04, except for the workers.  Similar to the above.

        ec2_manager.py -n dev04 -c start -w 1

Starts all of dev04, but only one worker.

        ec2_manager.py -n dev04 -w 4

Sets dev04 to have 4 workers total.  Will start/stop workers as required.  Will not create new workers (yet), so if you set the value for w greater than your number of workers it will just start all of them.  Requires the cluster to already be running.

        ec2_manager.py -n dev04 -m on

Sets all Matterhorn nodes on dev04 into maintenance mode.

        ec2_manager.py -n dev04 -m off

Takes all Matterhorn nodes on dev04 out of maintenance.

        ec2_manager.py -n dev04 -c stop

Places all Matterhorn nodes on dev04 into maintenance, then (once there are no more active jobs) shuts down the nodes, and then the Zadara array (if applicable).


Note: Some commands have precendence over others.  Currently, the order is:

Commands (-c) are processed first.  If a worker count (-w) is specified with the command it is processed at the same time.  If there is just a worker count specified then it is processed first.  In all cases, maintenance commands (-m) are processed last.

Installation
------------

Requires Python 2.6+ and Boto (http://boto.readthedocs.org/en/latest/)
