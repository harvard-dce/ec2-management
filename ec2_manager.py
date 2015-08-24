#!/usr/bin/env python

import sys
import logging

import click
click.disable_unicode_literals_warning = True

import utils
import settings
from controllers import EC2Controller

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
def exit_with_code(result, *args, **kwargs):
    exit_code = result[0]
    sys.exit(exit_code)

@cli.command()
@click.option('-f','--format', default='json', type=click.Choice(['json', 'table']))
@click.pass_obj
@utils.handle_exit
def status(ec2, format):
    """Output service job/queue status of a cluster"""
    stats = ec2.status_summary()
    click.echo(utils.format_status(stats, format))

@cli.command()
@click.option('-w', '--workers', type=int)
@click.pass_obj
@utils.handle_exit
@utils.log_before_after_stats
def start(ec2, workers):
    """Start a cluster"""
    ec2.start_cluster(workers)

@cli.command()
@click.pass_obj
@utils.handle_exit
@utils.log_before_after_stats
def stop(ec2):
    """Stop a cluster"""
    ec2.stop_cluster()

@cli.command()
@click.pass_obj
@utils.handle_exit
@utils.admin_is_up
@utils.log_before_after_stats
def autoscale(ec2):
    """Autoscale a cluster to the correct number of workers based on currently
    queued jobs"""
    ec2.autoscale()

@cli.command()
@click.argument('workers', type=int)
@click.pass_obj
@utils.handle_exit
@utils.admin_is_up
@utils.log_before_after_stats
def scale_to(ec2, workers):
    """Scale a cluster to a specified number of workers"""
    ec2.scale_to(workers)

@cli.command()
@click.argument('direction', type=click.Choice(['up', 'down']))
@click.option('-w', '--workers', type=int, default=1)
@click.pass_obj
@utils.handle_exit
@utils.admin_is_up
@utils.log_before_after_stats
def scale(ec2, direction, workers):
    """Incrementally scale a cluster up/down a specified number of workers"""
    ec2.scale(direction, num_workers=workers)

@cli.command()
@click.argument('state', type=click.Choice(['on', 'off']))
@click.pass_obj
@utils.handle_exit
@utils.admin_is_up
@utils.log_before_after_stats
def maintenance(ec2, state):
    """Enable/disable maintenance mode on a cluster"""
    if state == 'on':
        ec2.maintenance_on()
    elif state == 'off':
        ec2.maintenance_off()

if __name__ == "__main__":
    cli()
