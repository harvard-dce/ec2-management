
import click
import unittest
from mock import patch
from click.testing import CliRunner

import utils
from ec2_manager import cli
from controllers import EC2Controller

class CliTests(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

        @click.command()
        @click.argument('test')
        def foo(test_arg):
            return test_arg

        cli.add_command(foo)

    @patch.object(EC2Controller, '__init__')
    @patch.object(utils, 'init_logging')
    def test_cmd_group(self, mock_logging, mock_ec2):
        """
        ./ec2_manager.py dev99 foo
        RunContext should get 'dev99' as cluster name
        """
        import logging

        result = self.runner.invoke(cli, ['dev99', 'foo'])
        mock_ec2.assert_called_with('dev99', force=False, dry_run=False)
        mock_logging.assert_called_with('dev99', True, logging.INFO)

        # dry_run option
        result = self.runner.invoke(cli, ['-n', 'dev99', 'foo'])
        mock_ec2.assert_called_with('dev99', force=False, dry_run=True)

        # force option
        result = self.runner.invoke(cli, ['-f', 'dev99', 'foo'])
        mock_ec2.assert_called_with('dev99', force=True, dry_run=False)

        # debug option
        result = self.runner.invoke(cli, ['-d', 'dev99', 'foo'])
        mock_logging.assert_called_with('dev99', True, logging.DEBUG)

        # verbose option
        result = self.runner.invoke(cli, ['-q', 'dev99', 'foo'])
        mock_logging.assert_called_with('dev99', False, logging.INFO)

