import argparse

import utils
import settings
from controllers import AWSController, MatterhornController, ZadaraController


def main():
    parser = argparse.ArgumentParser(
        description="Control script for HUDCE AWS instances.  Maintenance (-m) commands take precedence over start/stop commands (-c), which in turn take precedence over worker (-w) commands.")
    instanceGroup = parser.add_argument_group('required instance options', 'Control which AWS instances are worked on.  Pick one or the other.')
    instanceGroup.add_argument(
        '-n', '--name', help='The name of the cluster to operate on.  This is a prefix, so something like dev02 is expected')

    parser.add_argument(
        '-c', '--command', help='The command to issue, currently either start or stop')
    parser.add_argument('-s', '--state', help='Filter based on state')
    parser.add_argument(
        '-m', '--maintenance', help='Control the Matterhorn instances\' maintenance state.  Options are on or off')
    parser.add_argument('-w', '--workers', type=int,
                        help='Set the number of workers to have in a cluster.  Effective with either the start command, or alone.')
    parser.add_argument(
        '-d', '--dryrun', help='Set this to true to do a dry run', action='store_true', default=False)
    parser.add_argument(
        '--force', help='Force the script to shut nodes down, even if they are on prod.  Does not override the dry run setting', action='store_true', default=False)
    # TODO: Applying tags?
    args = parser.parse_args()
    dryrun = args.dryrun
    command = args.command
    state = args.state
    maint = args.maintenance
    cluster = args.name
    workers = args.workers
    force = args.force

    if cluster == None:
        logPrefix = "ec2_manager-NOCLUSTER"
        logger = utils.setupLogger(logPrefix)
        logger.error("No cluster specified!")

    logPrefix = "ec2_manager-" + cluster
    logger = utils.setupLogger(logPrefix)

    if dryrun:
        logger.info("Dryrun mode enabled")

    if force:
        #Use the force Luke
        logger.info("Force mode enabled")

    if workers != None and workers < 0:
        logger.error("Number of workers must be zero or greater")
        return



    # Setup the connection
    z = ZadaraController(logPrefix, 
        dry_run=dryrun, security_token=settings.ZADARA_ACCOUNT_TOKEN)
    m = MatterhornController(logPrefix, dry_run=dryrun)
    c = AWSController(logPrefix, test=dryrun, force=force, region=settings.AWS_REGION,  aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                           aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY, matterhorn_controller=m, zadara_controller=z)

    try:
        # Process the commands
        if command == 'start':
            c.bringupCluster(cluster, workers)
        elif command == 'stop':
            c.bringdownCluster(cluster)

        if workers != None:
            c.ensureClusterHasWorkers(cluster, workers)

        if maint == 'on':
            targetMaintenanceState = True
            c.place_cluster_in_maintenance(cluster, targetMaintenanceState)
        elif maint == 'off':
            targetMaintenanceState = False
            c.place_cluster_in_maintenance(cluster, targetMaintenanceState)
    except Exception as e:
        logger.exception(e)

if __name__ == "__main__":
    main()
