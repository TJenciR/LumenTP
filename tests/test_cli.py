import argparse
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from lumentp import cli
from lumentp.message import HeaderMap, Response


class CLITests(unittest.TestCase):
    def test_build_parser_parses_submit_patch_and_filters(self):
        parser = cli.build_parser()
        args = parser.parse_args(["submit", "/doc", "--body", "hello", "--content-type", "text/plain", "--if-none-match", "*", "--meta", "kind=note"])
        self.assertEqual(args.command, "submit")
        self.assertEqual(args.target, "/doc")
        self.assertEqual(args.body, "hello")
        self.assertEqual(args.content_type, "text/plain")
        self.assertEqual(args.if_none_match, "*")
        self.assertEqual(args.meta, ["kind=note"])

        args = parser.parse_args(["patch", "/doc", "--content-type-update", "text/markdown", "--remove-meta", "kind"])
        self.assertEqual(args.content_type_update, "text/markdown")
        self.assertEqual(args.remove_meta, ["kind"])

        args = parser.parse_args(["list", "/docs", "--limit", "10", "--offset", "5", "--contains", "rep", "--filter-content-type", "text/*", "--sort", "version", "--desc"])
        self.assertEqual(args.limit, 10)
        self.assertEqual(args.offset, 5)
        self.assertTrue(args.desc)

    def test_run_client_command_dispatches_all_supported_methods(self):
        client = MagicMock()
        client.ping.return_value = "ping"
        client.fetch.return_value = "fetch"
        client.inspect.return_value = "inspect"
        client.list.return_value = "list"
        client.submit.return_value = "submit"
        client.replace.return_value = "replace"
        client.patch.return_value = "patch"
        client.remove.return_value = "remove"

        self.assertEqual(cli._run_client_command(client, SimpleNamespace(command="ping", request_id=None)), "ping")
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="fetch", target="/a", accept=None, token=None, if_none_match=None, byte_range=None, request_id=None),
            ),
            "fetch",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="inspect", target="/a", accept=None, token=None, if_none_match=None, request_id=None),
            ),
            "inspect",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="list", target="/a", accept="application/json", token=None, limit=10, offset=0, contains=None, filter_content_type=None, sort=None, desc=False, request_id=None),
            ),
            "list",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(
                    command="submit",
                    target="/a",
                    body="x",
                    content_type="text/plain",
                    token=None,
                    if_none_match=None,
                    if_match=None,
                    cache_control=None,
                    meta=[],
                    request_id=None,
                ),
            ),
            "submit",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(
                    command="replace",
                    target="/a",
                    body="x",
                    content_type="text/plain",
                    token=None,
                    if_match=None,
                    cache_control=None,
                    meta=[],
                    request_id=None,
                ),
            ),
            "replace",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(
                    command="patch",
                    target="/a",
                    content_type_update="text/plain",
                    cache_control=None,
                    meta=[],
                    remove_meta=[],
                    token=None,
                    if_match=None,
                    request_id=None,
                ),
            ),
            "patch",
        )
        self.assertEqual(
            cli._run_client_command(
                client,
                SimpleNamespace(command="remove", target="/a", token=None, if_match=None, request_id=None),
            ),
            "remove",
        )

    def test_run_client_command_rejects_unknown_command(self):
        with self.assertRaises(ValueError):
            cli._run_client_command(MagicMock(), argparse.Namespace(command="bad"))

    def test_parse_meta_pairs_rejects_invalid_items(self):
        with self.assertRaises(ValueError):
            cli._parse_meta_pairs(["bad"])
        self.assertEqual(cli._parse_meta_pairs(["a=1", "b=2"]), {"a": "1", "b": "2"})

    @patch("lumentp.cli.LumenTPClient")
    def test_main_client_command_prints_status_type_and_body(self, mock_client_class):
        mock_client = mock_client_class.return_value
        headers = HeaderMap.from_pairs([("Content-Type", "text/plain")])
        mock_client.fetch.return_value = Response(status_code=200, body=b"hello", headers=headers)

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["fetch", "/doc"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("200 OK", output)
        self.assertIn("text/plain", output)
        self.assertIn("hello", output)

    @patch("lumentp.cli.LumenTPClient")
    def test_main_show_headers_prints_non_length_headers(self, mock_client_class):
        mock_client = mock_client_class.return_value
        headers = HeaderMap.from_pairs([("Content-Type", "text/plain"), ("ETag", '"tag"')])
        mock_client.inspect.return_value = Response(status_code=200, headers=headers)

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["inspect", "/doc", "--show-headers"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn('ETag: "tag"', output)
        self.assertNotIn("Content-Length:", output)

    @patch("lumentp.cli.LumenTPClient")
    def test_main_client_command_without_body_prints_status_only(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.remove.return_value = Response(status_code=204)

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["remove", "/doc"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue().strip().splitlines()
        self.assertEqual(output, ["204 NO CONTENT"])

    @patch("lumentp.cli.LumenTPClient")
    def test_main_list_prints_json_payload(self, mock_client_class):
        mock_client = mock_client_class.return_value
        headers = HeaderMap.from_pairs([("Content-Type", "application/json")])
        mock_client.list.return_value = Response(status_code=200, body=b'{"items": []}', headers=headers)

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main(["list", "/docs"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("200 OK", output)
        self.assertIn('{"items": []}', output)

    @patch("lumentp.cli.LumenTPServer")
    @patch("lumentp.cli.time.sleep", side_effect=KeyboardInterrupt)
    def test_main_server_command_starts_and_stops_server(self, _mock_sleep, mock_server_class):
        mock_server = mock_server_class.return_value

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = cli.main([
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                "9090",
                "--read-token",
                "reader",
                "--write-token",
                "writer",
                "--admin-token",
                "admin",
                "--cache-max-age",
                "10",
            ])

        self.assertEqual(exit_code, 0)
        mock_server.start.assert_called_once()
        mock_server.stop.assert_called_once()
        output = stdout.getvalue()
        self.assertIn("LumenTP server listening on 127.0.0.1:9090", output)
        self.assertIn("stopping server", output)
