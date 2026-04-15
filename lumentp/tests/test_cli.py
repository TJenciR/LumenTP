import argparse
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lumentp import cli
from lumentp.message import Response


class CLITests(unittest.TestCase):
    def test_build_parser_parses_submit(self):
        parser = cli.build_parser()
        args = parser.parse_args(["submit", "/doc", "--body", "hello", "--content-type", "text/plain"])
        self.assertEqual(args.command, "submit")
        self.assertEqual(args.target, "/doc")
        self.assertEqual(args.body, "hello")
        self.assertEqual(args.content_type, "text/plain")

    def test_run_client_command_dispatches_all_supported_methods(self):
        client = MagicMock()
        client.ping.return_value = "ping"
        client.fetch.return_value = "fetch"
        client.submit.return_value = "submit"
        client.replace.return_value = "replace"
        client.remove.return_value = "remove"

        self.assertEqual(cli._run_client_command(client, SimpleNamespace(command="ping")), "ping")
        self.assertEqual(
            cli._run_client_command(client, SimpleNamespace(command="fetch", target="/a", accept=None, token=None)),
            "fetch",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="submit", target="/a", body="x", content_type="text/plain", token=None),
            ),
            "submit",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="replace", target="/a", body="x", content_type="text/plain", token=None),
            ),
            "replace",
        )
        self.assertEqual(cli._run_client_command(client, SimpleNamespace(command="remove", target="/a", token=None)), "remove")

    def test_run_client_command_rejects_unknown_command(self):
        with self.assertRaises(ValueError):
            cli._run_client_command(MagicMock(), argparse.Namespace(command="bad"))

    @patch("lumentp.cli.LumenTPClient")
    def test_main_client_command_prints_status_type_and_body(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.fetch.return_value = Response(
            status_code=200,
            body=b"hello",
            headers=Response(status_code=200).headers.with_replaced("Content-Type", "text/plain"),
        )

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["fetch", "/doc"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("200 OK", output)
        self.assertIn("text/plain", output)
        self.assertIn("hello", output)

    @patch("lumentp.cli.LumenTPClient")
    def test_main_client_command_without_body_prints_status_and_type(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.remove.return_value = Response(status_code=204)

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["remove", "/doc"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue().strip().splitlines()
        self.assertEqual(output, ["204 NO CONTENT"])

    @patch("lumentp.cli.LumenTPServer")
    @patch("lumentp.cli.time.sleep", side_effect=KeyboardInterrupt)
    def test_main_server_command_starts_and_stops_server(self, _mock_sleep, mock_server_class):
        mock_server = mock_server_class.return_value

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["server", "--host", "127.0.0.1", "--port", "9090", "--token", "secret"])

        self.assertEqual(exit_code, 0)
        mock_server.start.assert_called_once()
        mock_server.stop.assert_called_once()
        output = stdout.getvalue()
        self.assertIn("LumenTP server listening on 127.0.0.1:9090", output)
        self.assertIn("stopping server", output)
