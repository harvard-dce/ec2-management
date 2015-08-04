
import unittest
import click
from mock import patch
from click.testing import CliRunner

from ec2_manager import cli, RunContext

class CliTests(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

        @click.command()
        @click.argument('test')
        def foo(test_arg):
            return test_arg

        cli.add_command(foo)

    @patch.object(RunContext, '__init__')
    @patch('utils.init_logging')
    def test_cmd_group(self, mock_init_logging, mock_const):
        """
        ./ec2_manager.py dev99 foo
        RunContext should get 'dev99' as cluster name
        """
        import logging

        result = self.runner.invoke(cli, ['dev99', 'foo'])
        mock_const.assert_called_with('dev99', False)
        mock_init_logging.assert_called_with('dev99', True, logging.INFO)

        # dry_run option
        result = self.runner.invoke(cli, ['-n', 'dev99', 'foo'])
        mock_const.assert_called_with('dev99', True)

        # debug option
        result = self.runner.invoke(cli, ['-d', 'dev99', 'foo'])
        mock_init_logging.assert_called_with('dev99', True, logging.DEBUG)

        # verbose option
        result = self.runner.invoke(cli, ['-q', 'dev99', 'foo'])
        mock_init_logging.assert_called_with('dev99', False, logging.INFO)


    def test_status_cmd(self):
        """
        ./ec2_manager.py dev99 status
        """

        result = self.runner.invoke(cli, ['dev99', 'status'])

