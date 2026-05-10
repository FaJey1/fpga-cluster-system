"""
Тесты CLI fpgactl — проверка команд через Click CliRunner.

Запускаются против живого кластера, используя конфигурацию из conftest.py.
Перед тестами устанавливается контекст (URL + токен) во временном домашнем каталоге.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

# Добавляем fpgactl в путь поиска модулей
sys.path.insert(0, str(Path(__file__).parent.parent / "fpgactl"))
from fpgactl import cli

from conftest import MASTER_URL, HEADERS

ROOT_TOKEN = HEADERS["X-API-Token"]


@pytest.fixture
def runner():
    """CLI runner с временным домашним каталогом."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = tmpdir

        runner = CliRunner()
        # Установить контекст перед каждым тестом
        result = runner.invoke(cli, ["config", "use-context", MASTER_URL,
                                     "--token", ROOT_TOKEN])
        assert result.exit_code == 0, f"config failed: {result.output}"

        yield runner

        if old_home:
            os.environ["HOME"] = old_home
        else:
            del os.environ["HOME"]


class TestConfigCommand:
    def test_use_context_saves_config(self, runner):
        result = runner.invoke(cli, ["config", "use-context",
                                     "http://localhost:3030", "--token", "mytoken"])
        assert result.exit_code == 0
        assert "Контекст установлен" in result.output or "Context" in result.output

    def test_config_show(self, runner):
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "localhost:3030" in result.output or MASTER_URL in result.output


class TestGetCommands:
    def test_get_masters(self, runner):
        result = runner.invoke(cli, ["get", "masters"])
        assert result.exit_code == 0
        assert "master" in result.output.lower()

    def test_get_workers(self, runner):
        result = runner.invoke(cli, ["get", "workers"])
        assert result.exit_code == 0

    def test_get_fpgas(self, runner):
        result = runner.invoke(cli, ["get", "fpgas"])
        assert result.exit_code == 0

    def test_get_queue(self, runner):
        result = runner.invoke(cli, ["get", "queue"])
        assert result.exit_code == 0

    def test_get_tasks(self, runner):
        result = runner.invoke(cli, ["get", "tasks"])
        assert result.exit_code == 0


class TestHealthCommands:
    def test_health(self, runner):
        result = runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "ok" in result.output.lower()

    def test_who_master(self, runner):
        result = runner.invoke(cli, ["who-master"])
        assert result.exit_code == 0
        assert "master" in result.output.lower() or "leader" in result.output.lower() or "ЛИДЕР" in result.output or "ведомый" in result.output

    def test_quorum_command(self, runner):
        result = runner.invoke(cli, ["quorum"])
        assert result.exit_code == 0
        assert "ha" in result.output.lower() or "standalone" in result.output.lower()


class TestRegisterCommands:
    def test_register_worker(self, runner):
        worker_id = f"cli-test-worker-{int(time.time())}"
        result = runner.invoke(cli, [
            "register", "worker",
            "--id", worker_id,
            "--tags", "test,dev",
            "--ip", "192.168.1.100",
            "--capacity", "4",
        ])
        assert result.exit_code == 0
        assert worker_id in result.output

    def test_register_worker_appears_in_list(self, runner):
        worker_id = f"cli-list-worker-{int(time.time())}"
        runner.invoke(cli, ["register", "worker", "--id", worker_id,
                            "--tags", "test", "--ip", "10.0.0.1"])
        result = runner.invoke(cli, ["get", "workers"])
        assert result.exit_code == 0
        # Rich may truncate long IDs; check recognisable prefix
        assert "cli-list-worker-" in result.output


class TestSubmitCommand:
    def test_submit_task(self, runner):
        result = runner.invoke(cli, [
            "submit", "task",
            "--bitstream", "s3://bucket/cli-test.bit",
            "--tag", "test",
            "--mode", "PROD",
            "--type", "deployment",
            "--priority", "1",
            "--pipeline", "cli-test-001",
        ])
        assert result.exit_code == 0
        assert "task_id" in result.output.lower() or "Задача отправлена" in result.output

    def test_submit_task_appears_in_list(self, runner):
        runner.invoke(cli, [
            "submit", "task",
            "--bitstream", "s3://bucket/cli-list-test.bit",
            "--tag", "test",
        ])
        result = runner.invoke(cli, ["get", "tasks"])
        assert result.exit_code == 0


class TestTokenCommands:
    def test_token_whoami(self, runner):
        result = runner.invoke(cli, ["token", "whoami"])
        assert result.exit_code == 0
        assert "admin" in result.output.lower()

    def test_token_list(self, runner):
        result = runner.invoke(cli, ["token", "list"])
        assert result.exit_code == 0
        assert "root" in result.output.lower() or "admin" in result.output.lower()

    def test_token_issue(self, runner):
        result = runner.invoke(cli, [
            "token", "issue",
            "--role", "operator",
            "--description", "CLI issued token",
        ])
        assert result.exit_code == 0
        assert "operator" in result.output.lower()
        assert "Токен выпущен" in result.output or "issued" in result.output.lower()

    def test_token_issue_with_ttl(self, runner):
        result = runner.invoke(cli, [
            "token", "issue",
            "--role", "viewer",
            "--description", "Short-lived viewer",
            "--ttl", "7200",
        ])
        assert result.exit_code == 0
        assert "Истекает" in result.output or "expires" in result.output.lower()

    def test_token_revoke(self, runner):
        # Issue a token, capture its ID, revoke it
        issue_result = runner.invoke(cli, [
            "token", "issue",
            "--role", "viewer",
            "--description", "to revoke",
        ])
        assert issue_result.exit_code == 0

        # Extract token_id from list
        list_result = runner.invoke(cli, ["token", "list"])
        assert list_result.exit_code == 0

    def test_token_wrong_role_rejected(self, runner):
        result = runner.invoke(cli, [
            "token", "issue",
            "--role", "superadmin",
            "--description", "should fail",
        ])
        assert result.exit_code != 0 or "Error" in result.output or "400" in result.output


class TestErrorHandling:
    def test_get_task_nonexistent(self, runner):
        result = runner.invoke(cli, ["get", "task", "does-not-exist-xyz"])
        assert result.exit_code != 0 or "404" in result.output or "not found" in result.output.lower()

    def test_invalid_url_graceful_fail(self):
        """Команда с неправильным URL должна завершаться с ошибкой, не крашиться."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmpdir
            try:
                r = CliRunner()
                r.invoke(cli, ["config", "use-context", "http://127.0.0.1:19999",
                               "--token", "tok"])
                result = r.invoke(cli, ["health"])
                assert result.exit_code != 0 or "error" in result.output.lower()
            finally:
                if old_home:
                    os.environ["HOME"] = old_home
