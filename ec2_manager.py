import argparse
import logging
import click

import utils
import settings
from controllers import AWSController, MatterhornController, ZadaraController

class RunContext(object):

    def __init__(self, cluster, dry_run):
        self.cluster = cluster
        self.dry_run = dry_run
        # self.z = ZadaraController(cluster,
        #                      security_token=settings.ZADARA_ACCOUNT_TOKEN)
        # self.m = MatterhornController(cluster)
        # self.aws = AWSController(cluster,
        #                         region=settings.AWS_REGION,
        #                         aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        #                         aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        #                         matterhorn_controller=self.m,
        #                         zadara_controller=self.z)


@click.group()
@click.argument('cluster')
@click.option('-v/-q','--verbose/--quiet', is_flag=True, default=True)
@click.option('-d','--debug', is_flag=True)
@click.option('-n','--dryrun', is_flag=True)
@click.pass_context
def cli(ctx, cluster, verbose, debug, dryrun):
    log_level = debug and logging.DEBUG or logging.INFO
    log = utils.init_logging(cluster, verbose, log_level)
    log.debug("Command: %s %s, options: %s",
              ctx.info_name, ctx.invoked_subcommand, ctx.params)
    ctx.obj = RunContext(cluster, dryrun)

@cli.command()
@click.pass_obj
def status(ctx_obj):
    """Display service job/queue status of a cluster"""
    aws = AWSController(ctx_obj.cluster, dry_run=ctx_obj.dry_run)
    pass

@cli.command()
@click.option('-w', '--workers', type=int, prompt=True, default=4)
@click.pass_context
def start(ctx, workers):
    """Start a cluster"""
    ctx.obj.aws.bringupCluster(ctx.obj.cluster, workers)

@cli.command()
@click.pass_context
def stop(ctx):
    """Stop a cluster"""
    ctx.obj.aws.bringdownCluster(ctx.obj.cluster)

@cli.command()
@click.pass_context
def autoscale(ctx):
    """Autoscale a cluster to the correct number of workers based on currently
    queued jobs"""
    pass

@cli.command()
@click.pass_context
@click.argument('workers', type=int)
def scale_to(ctx, workers):
    """Scale a cluster to a specified number of workers"""
    ctx.obj.aws.ensureClusterHasWorkers(ctx.obj.cluster, workers)

@cli.command()
@click.argument('direction', type=click.Choice(['up', 'down']))
@click.option('-w', '--workers', type=int, prompt=True, default=1)
@click.pass_context
def scale(ctx, direction, workers):
    """Incrementally scale a cluster up/down a specified number of workers"""
    pass

@cli.command()
@click.argument('state', type=click.Choice(['on', 'off']))
@click.pass_context
def maintenance(ctx, state):
    """Enable/disable maintenance mode on a cluster"""
    if state == 'on':
        ctx.obj.aws.place_cluster_in_maintenance(ctx.obj.cluster, True)
    elif state == 'off':
        ctx.obj.aws.place_cluster_in_maintenance(ctx.obj.cluster, False)


if __name__ == "__main__":
    cli()
