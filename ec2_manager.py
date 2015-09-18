#!/usr/bin/env python

import sys
import logging
from functools import wraps

import click
click.disable_unicode_literals_warning = True

import utils
import settings
from controllers import ec2, ClusterException, \
    EC2Controller, \
    OpsworksController

log = logging.getLogger('ec2-manager')

def handle_exit(cmd):
    """
    execute the command and catch any cluster exceptions. The return value
    will be used as the arg for sys.exit().
    """
    @wraps(cmd)
    def wrapped(cluster, *args, **kwargs):
        try:
            cmd(cluster, *args, **kwargs)
            return 0
        except ClusterException, e:
            log.info(str(e))
            return str(e)
    return wrapped

@click.group(chain=True)
@click.argument('prefix')
@click.option('-v/-q','--verbose/--quiet', is_flag=True, default=True)
@click.option('-d','--debug', is_flag=True)
@click.option('-n','--dry-run', is_flag=True)
@click.option('-f', '--force', is_flag=True)
@click.option('-o', '--opsworks', is_flag=True)
@click.version_option(settings.VERSION)
@click.pass_context
def cli(ctx, prefix, verbose, debug, dry_run, force, opsworks):

    log_level = debug and logging.DEBUG or logging.INFO
    utils.init_logging(prefix, verbose, log_level)
    log.debug("Command: %s %s, options: %s",
              ctx.info_name, ctx.invoked_subcommand, ctx.params)
    if dry_run:
        log.info("Dry run enabled!")

    if opsworks:
        cluster = OpsworksController(prefix, force=force, dry_run=dry_run)
        ctx.meta['opsworks'] = True
    else:
        cluster = EC2Controller(prefix, force=force, dry_run=dry_run)

    # attach controller to the context for subcommand use
    ctx.obj = cluster

@cli.resultcallback()
def exit_with_code(result, *args, **kwargs):
    exit_code = result[0]
    sys.exit(exit_code)

@cli.command()
@click.option('-f','--format', default='json', type=click.Choice(['json', 'table']))
@click.pass_obj
@handle_exit
def status(cluster, format):
    """Output service job/queue status of a cluster"""
    stats = cluster.status_summary()
    click.echo(utils.format_status(stats, format))

@cli.command()
@click.option('-w', '--workers', type=int)
@click.pass_obj
@utils.opsworks_verboten
@handle_exit
@ec2.log_before_after_stats
def start(cluster, workers):
    """Start a cluster"""
    cluster.start_cluster(workers)

@cli.command()
@click.pass_obj
@utils.opsworks_verboten
@handle_exit
@ec2.log_before_after_stats
def stop(cluster):
    """Stop a cluster"""
    cluster.stop_cluster()

@cli.command()
@click.pass_obj
@handle_exit
@ec2.admin_is_up
@ec2.log_before_after_stats
def autoscale(cluster):
    """Autoscale a cluster to the correct number of workers based on currently
    queued jobs"""
    cluster.autoscale()

@cli.command()
@click.argument('workers', type=int)
@click.pass_obj
@handle_exit
@ec2.admin_is_up
@ec2.log_before_after_stats
def scale_to(cluster, workers):
    """Scale a cluster to a specified number of workers"""
    cluster.scale_to(workers)

@cli.command()
@click.argument('direction', type=click.Choice(['up', 'down']))
@click.option('-w', '--workers', type=int, default=1)
@click.pass_obj
@handle_exit
@ec2.admin_is_up
@ec2.log_before_after_stats
def scale(cluster, direction, workers):
    """Incrementally scale a cluster up/down a specified number of workers"""
    cluster.scale(direction, num_workers=workers)

@cli.command()
@click.argument('state', type=click.Choice(['on', 'off']))
@click.pass_obj
@handle_exit
@ec2.admin_is_up
@ec2.log_before_after_stats
def maintenance(cluster, state):
    """Enable/disable maintenance mode on a cluster"""
    if state == 'on':
        cluster.maintenance_on()
    elif state == 'off':
        cluster.maintenance_off()

if __name__ == "__main__":
    cli()
