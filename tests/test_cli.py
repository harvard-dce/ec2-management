
import click
click.disable_unicode_literals_warning = True

import logging
import unittest
from mock import patch
from click.testing import CliRunner

import utils
import ec2_manager
from ec2_manager import cli, handle_exit
from controllers.ec2 import log_before_after_stats, admin_is_up
import controllers

@patch.object(utils, 'init_logging', autospec=True)
@patch.object(ec2_manager, 'EC2Controller', autospec=True)
class CliTests(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

        # fake command for testing general cli options/args
        @click.command()
        @click.pass_obj
        def foo(ec2):
            pass
        cli.add_command(foo)

        # fake command for testing before/after summary log
        @click.command()
        @click.pass_obj
        @log_before_after_stats
        def bar(ec2):
            pass
        cli.add_command(bar)

        # fake command for testing exit handling
        @click.command()
        @click.option('--exc_type', default=None)
        @click.pass_obj
        @handle_exit
        def baz(ec2, exc_type=None):
            if exc_type is None:
                pass
            else:
                exc_type = eval(exc_type)
                raise exc_type('Boom!')
        cli.add_command(baz)

    def tearDown(self):
        for fake_cmd in ['foo','bar','baz']:
            del cli.commands[fake_cmd]

    def test_cmd_group_basic(self, mock_controller, mock_init_logging):

        result = self.runner.invoke(cli, ['dev99', 'foo'])
        mock_controller.assert_called_once_with('dev99', force=False, dry_run=False)
        mock_init_logging.assert_called_once_with('dev99', True, logging.INFO)

    def test_cmd_group_dryrun(self, mock_controller, mock_init_logging):

        # dry_run option
        result = self.runner.invoke(cli, ['-n', 'dev99', 'foo'])
        mock_controller.assert_called_once_with('dev99', force=False, dry_run=True)

    def test_cmd_group_force(self, mock_controller, mock_init_logging):
        # force option
        result = self.runner.invoke(cli, ['-f', 'dev99', 'foo'])
        mock_controller.assert_called_once_with('dev99', force=True, dry_run=False)

    def test_cmd_group_debug(self, mock_controller, mock_init_logging):
        # debug option
        result = self.runner.invoke(cli, ['-d', 'dev99', 'foo'])
        mock_init_logging.assert_called_with('dev99', True, logging.DEBUG)

    def test_cmd_group_quiet(self, mock_controller, mock_init_logging):
        # quiet option
        result = self.runner.invoke(cli, ['-q', 'dev99', 'foo'])
        mock_init_logging.assert_called_with('dev99', False, logging.INFO)

    @patch.object(utils, 'log_status_summary', autospec=True)
    def test_before_after_logging(self, mock_log_status, mock_controller, mock_init_logging):
        # test that before/after stats logging is executed
        result = self.runner.invoke(cli, ['dev99', 'bar'])
        self.assertEqual(mock_log_status.call_count, 2)
        call1 = mock_log_status.call_args_list[0][0]
        self.assertEqual(call1[1], 'Before')
        call2 = mock_log_status.call_args_list[1][0]
        self.assertEqual(call2[1], 'After')

    def test_handle_exit(self, mock_controller, mock_init_logging):

        result = self.runner.invoke(cli, ['dev99', 'baz'])
        self.assertEqual(result.exit_code, 0)

        # ClusterException raised during command invocation should be caught
        # and result in a sys.exit with the exception
        result = self.runner.invoke(cli, ['dev99', 'baz', '--exc_type', 'controllers.ClusterException'])
        self.assertEqual(result.exit_code, 1)
        self.assertIsInstance(result.exception, SystemExit)
        self.assertEqual(result.exception.message, 'Boom!')

        # simulate any other type of unexpected execption
        result = self.runner.invoke(cli, ['dev99', 'baz', '--exc_type', 'KeyError'])
        self.assertEqual(result.exit_code, -1)
        self.assertIsInstance(result.exception, KeyError)
