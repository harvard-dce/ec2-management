#!/usr/bin/env python

import sys
import logging

import click
click.disable_unicode_literals_warning = True

import utils
import settings
from controllers import EC2Controller
from controllers.exceptions import ClusterException

log = logging.getLogger('ec2-manager')


@click.group(chain=True)
@click.argument('cluster')
@click.option('-v/-q','--verbose/--quiet', is_flag=True, default=True)
@click.option('-d','--debug', is_flag=True)
@click.option('-n','--dry-run', is_flag=True)
@click.option('-f', '--force', is_flag=True)
@click.version_option(settings.VERSION)
@click.pass_context
def cli(ctx, cluster, verbose, debug, dry_run, force):

    log_level = debug and logging.DEBUG or logging.INFO
    utils.init_logging(cluster, verbose, log_level)
    log.debug("Command: %s %s, options: %s",
              ctx.info_name, ctx.invoked_subcommand, ctx.params)
    if dry_run:
        log.info("Dry run enabled!")

    ec2 = EC2Controller(cluster, force=force, dry_run=dry_run)

    # attach controller to the context for subcommand use
    ctx.obj = ec2

@cli.resultcallback()
def exit_with_code(exit_code, *args, **kwargs):
    sys.exit(exit_code)

@cli.command()
@click.option('-f','--format', default='json', type=click.Choice(['json', 'table']))
@click.pass_obj
def status(ec2, format):
    """Output service job/queue status of a cluster"""
    stats = ec2.status_summary()
    click.echo(utils.format_status(stats, format))
    return 0

@cli.command()
@click.option('-w', '--workers', type=int)
@click.pass_obj
@utils.log_before_after_stats
def start(ec2, workers):
    """Start a cluster"""
    if workers is None:
        workers = settings.MIN_WORKERS
    try:
        ec2.start_cluster(workers)
        return 0
    except ClusterException, e:
        log.error(str(e))
        click.echo(str(e))
        return 1

@cli.command()
@click.pass_obj
@utils.log_before_after_stats
def stop(ec2):
    """Stop a cluster"""
    try:
        ec2.stop_cluster()
        return 0
    except ClusterException, e:
        log.error(str(e))
        click.echo(str(e))
        return 1

@cli.command()
@click.pass_obj
@utils.log_before_after_stats
def autoscale(ec2):
    """Autoscale a cluster to the correct number of workers based on currently
    queued jobs"""
    try:
        ec2.autoscale()
        return 0
    except ClusterException, e:
        log.error(str(e))
        click.echo(str(e))
        return 1

@cli.command()
@click.argument('workers', type=int)
@click.pass_obj
@utils.log_before_after_stats
def scale_to(ec2, workers):
    """Scale a cluster to a specified number of workers"""
    raise NotImplementedError()

@cli.command()
@click.argument('direction', type=click.Choice(['up', 'down']))
@click.option('-w', '--workers', type=int, prompt=True, default=1)
@click.pass_obj
@utils.log_before_after_stats
def scale(ec2, direction, workers):
    """Incrementally scale a cluster up/down a specified number of workers"""
    try:
        ec2.scale(direction, num_workers=workers)
        return 0
    except ClusterException, e:
        log.error(str(e))
        click.echo(str(e))
        return 1

@cli.command()
@click.argument('state', type=click.Choice(['on', 'off']))
@click.pass_obj
@utils.log_before_after_stats
def maintenance(ec2, state):
    """Enable/disable maintenance mode on a cluster"""
    try:
        if state == 'on':
            ec2.maintenance_on()
        elif state == 'off':
            ec2.maintenance_off()
        return 0
    except ClusterException, e:
        log.error(str(e))
        click.echo(str(e))
        return 1

if __name__ == "__main__":
    cli()
