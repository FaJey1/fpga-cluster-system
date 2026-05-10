#!/usr/bin/env python3
"""
fpgactl — CLI tool for managing the FPGA cluster (kubectl-style).

Usage:
  fpgactl config use-context http://localhost:3030 --token secret-token
  fpgactl get workers
  fpgactl get masters
  fpgactl get fpgas
  fpgactl get queue
  fpgactl get tasks
  fpgactl get task <task_id>
  fpgactl register worker --id worker-1 --tags test,prod --ip 172.20.0.10
  fpgactl register fpga --id fpga-1 --worker worker-1 --model xc7a100t --vendor Xilinx --serial SN001 --interface usb
  fpgactl submit task --bitstream s3://bucket/file.bit --tag test --mode PROD
  fpgactl who-master
  fpgactl quorum
  fpgactl health
  fpgactl token issue --role operator --description "CI/CD token" --ttl 3600
  fpgactl token list
  fpgactl token revoke <token_id>
  fpgactl token whoami
  fpgactl task clear [--yes]
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import print as rprint

CONFIG_FILE = Path.home() / ".fpgactl" / "config.json"
console = Console()


# ── Config helpers ────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"url": "http://localhost:3030", "token": ""}


def save_config(config: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_client() -> httpx.Client:
    cfg = load_config()
    headers = {}
    if cfg.get("token"):
        headers["X-API-Token"] = cfg["token"]
    return httpx.Client(base_url=cfg["url"], headers=headers, timeout=15)


# ── Root ──────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """fpgactl — FPGA Cluster Management CLI"""


# ── config ────────────────────────────────────────────────────────────────

@cli.command("config")
@click.argument("subcommand")
@click.argument("value", required=False)
@click.option("--token", default="", help="API auth token")
def config_cmd(subcommand, value, token):
    """Configure cluster connection. Subcommands: use-context, show"""
    if subcommand == "use-context":
        cfg = {"url": value or "http://localhost:3030", "token": token}
        save_config(cfg)
        console.print(f"[green]Контекст установлен:[/green] {cfg['url']}")
    elif subcommand == "show":
        cfg = load_config()
        console.print(f"URL: [cyan]{cfg.get('url')}[/cyan]")
        tok = cfg.get("token", "")
        console.print(f"Токен: [dim]{tok[:8]}…[/dim]" if len(tok) > 8 else f"Токен: {tok or '(не задан)'}")
    else:
        console.print(f"[red]Неизвестная подкоманда:[/red] {subcommand}")
        sys.exit(1)


# ── get ───────────────────────────────────────────────────────────────────

@cli.group()
def get():
    """Получить ресурсы кластера."""


@get.command("workers")
def get_workers():
    """Список зарегистрированных воркеров."""
    with get_client() as client:
        r = client.get("/get_workers")
        r.raise_for_status()
    workers = r.json()
    if not workers:
        console.print("[yellow]Нет зарегистрированных воркеров[/yellow]")
        return
    t = Table(title="Воркеры")
    for col in ("worker_id", "tags", "status", "fpga_count", "node_ip"):
        t.add_column(col)
    for w in workers:
        t.add_row(
            w.get("worker_id", "-"),
            str(w.get("tags", [])),
            w.get("status", "-"),
            str(w.get("fpga_count", "-")),
            w.get("node_ip", "-"),
        )
    console.print(t)


@get.command("masters")
def get_masters():
    """Список мастер-узлов."""
    with get_client() as client:
        r = client.get("/get_masters")
        r.raise_for_status()
    masters = r.json()
    if not masters:
        console.print("[yellow]Нет мастер-узлов[/yellow]")
        return
    t = Table(title="Мастер-узлы")
    for col in ("node_id", "standalone"):
        t.add_column(col)
    for m in masters:
        t.add_row(str(m.get("node_id", "-")), str(m.get("standalone", "-")))
    console.print(t)


@get.command("fpgas")
def get_fpgas():
    """Список зарегистрированных ПЛИС."""
    with get_client() as client:
        r = client.get("/fpgas")
        r.raise_for_status()
    fpgas = r.json()
    if not fpgas:
        console.print("[yellow]Нет зарегистрированных ПЛИС[/yellow]")
        return
    t = Table(title="Устройства ПЛИС")
    for col in ("fpga_id", "model", "vendor", "interface", "status", "worker_id"):
        t.add_column(col)
    for f in fpgas:
        t.add_row(
            f.get("fpga_id", "-"), f.get("model", "-"), f.get("vendor", "-"),
            f.get("interface", "-"), f.get("status", "-"), f.get("worker_id", "-"),
        )
    console.print(t)


@get.command("queue")
def get_queue():
    """Показать очередь проектов."""
    with get_client() as client:
        r = client.get("/get_queue")
        r.raise_for_status()
    queue = r.json().get("queue", [])
    console.print(f"Глубина очереди: [bold]{len(queue)}[/bold]")
    for item in queue:
        rprint(item)


@get.command("tasks")
def get_tasks():
    """Список задач."""
    with get_client() as client:
        r = client.get("/tasks")
        r.raise_for_status()
    tasks = r.json()
    if not tasks:
        console.print("[yellow]Задач нет[/yellow]")
        return
    t = Table(title="Задачи")
    for col in ("task_id", "type", "mode", "worker_tag", "status", "priority"):
        t.add_column(col)
    for task in tasks:
        t.add_row(
            task.get("task_id", "-")[:12] + "…",
            task.get("type", "-"), task.get("mode", "-"),
            task.get("worker_tag", "-"), task.get("status", "-"),
            str(task.get("priority", "-")),
        )
    console.print(t)


@get.command("task")
@click.argument("task_id")
def get_task(task_id):
    """Детали задачи."""
    with get_client() as client:
        r = client.get(f"/tasks/{task_id}")
        r.raise_for_status()
    rprint(r.json())


# ── register ──────────────────────────────────────────────────────────────

@cli.group()
def register():
    """Зарегистрировать ресурсы кластера."""


@register.command("worker")
@click.option("--id", "worker_id", required=True)
@click.option("--tags", default="test", help="Теги через запятую")
@click.option("--ip", default="", help="IP-адрес воркера")
@click.option("--capacity", default=4, type=int)
def register_worker(worker_id, tags, ip, capacity):
    """Зарегистрировать воркер."""
    payload = {
        "worker_id": worker_id,
        "tags": tags.split(","),
        "node_ip": ip,
        "status": "online",
        "max_capacity": capacity,
    }
    with get_client() as client:
        r = client.post("/workers/register", json=payload)
        r.raise_for_status()
    console.print(f"[green]Воркер зарегистрирован:[/green] {worker_id}")
    rprint(r.json())


@register.command("fpga")
@click.option("--id", "fpga_id", required=True)
@click.option("--worker", "worker_id", required=True)
@click.option("--model", required=True)
@click.option("--vendor", default="Xilinx")
@click.option("--serial", default="")
@click.option("--interface", default="usb",
              type=click.Choice(["usb", "ethernet", "jtag", "pcie"]))
@click.option("--board", "board_name", default="", help="Имя отладочной платы (board_name)")
def register_fpga(fpga_id, worker_id, model, vendor, serial, interface, board_name):
    """Зарегистрировать ПЛИС."""
    payload = {
        "fpga_id": fpga_id, "worker_id": worker_id,
        "model": model, "vendor": vendor,
        "serial_number": serial, "interface": interface,
        "board_name": board_name,
    }
    with get_client() as client:
        r = client.post("/fpgas/register", json=payload)
        r.raise_for_status()
    console.print(f"[green]ПЛИС зарегистрирована:[/green] {fpga_id}")
    rprint(r.json())


# ── submit ────────────────────────────────────────────────────────────────

@cli.group()
def submit():
    """Отправить задачу в кластер."""


@submit.command("task")
@click.option("--bitstream", required=True, help="URL битстрима (S3/HTTP)")
@click.option("--tag", "worker_tag", default="test")
@click.option("--mode", default="PROD", type=click.Choice(["PROD", "TEST"]))
@click.option("--type", "task_type", default="deployment",
              type=click.Choice(["deployment", "test", "rollback"]))
@click.option("--fpga", "target_fpga_id", default="")
@click.option("--priority", default=2, type=int)
@click.option("--pipeline", "pipeline_id", default="manual")
def submit_task(bitstream, worker_tag, mode, task_type, target_fpga_id, priority, pipeline_id):
    """Отправить задачу развёртывания/тестирования."""
    payload = {
        "type": task_type, "mode": mode, "bitstream_url": bitstream,
        "target_fpga_id": target_fpga_id, "worker_tag": worker_tag,
        "priority": priority, "pipeline_id": pipeline_id,
    }
    with get_client() as client:
        r = client.post("/tasks", json=payload)
        r.raise_for_status()
    task = r.json()
    console.print(f"[green]Задача отправлена:[/green] {task['task_id']}")
    rprint(task)


# ── token ─────────────────────────────────────────────────────────────────

@cli.group()
def token():
    """Управление токенами доступа."""


@token.command("issue")
@click.option("--role", required=True, type=click.Choice(["admin", "operator", "viewer"]),
              help="Роль токена")
@click.option("--description", default="", help="Описание")
@click.option("--ttl", "ttl_seconds", default=None, type=int,
              help="TTL в секундах (по умолчанию — бессрочный)")
def token_issue(role, description, ttl_seconds):
    """Выпустить новый токен (только admin)."""
    payload = {"role": role, "description": description, "ttl_seconds": ttl_seconds}
    with get_client() as client:
        r = client.post("/auth/tokens", json=payload)
        r.raise_for_status()
    data = r.json()
    console.print(f"[green]Токен выпущен:[/green] {data['token_id']}")
    console.print(f"Роль: [cyan]{data['role']}[/cyan]")
    console.print(f"Токен: [bold yellow]{data['token']}[/bold yellow]")
    if data.get("expires_at"):
        import datetime
        exp = datetime.datetime.fromtimestamp(data["expires_at"]).isoformat()
        console.print(f"Истекает: {exp}")
    else:
        console.print("Срок действия: бессрочный")


@token.command("list")
def token_list():
    """Список активных токенов (только admin)."""
    with get_client() as client:
        r = client.get("/auth/tokens")
        r.raise_for_status()
    tokens = r.json()
    if not tokens:
        console.print("[yellow]Токенов нет[/yellow]")
        return
    t = Table(title="Токены доступа")
    for col in ("token_id", "role", "description", "is_root", "expires_at"):
        t.add_column(col)
    for tok in tokens:
        exp = str(tok.get("expires_at") or "бессрочный")
        t.add_row(
            tok.get("token_id", "-")[:16],
            tok.get("role", "-"),
            tok.get("description", "-"),
            str(tok.get("is_root", False)),
            exp,
        )
    console.print(t)


@token.command("revoke")
@click.argument("token_id")
def token_revoke(token_id):
    """Отозвать токен по ID (только admin; root-токен нельзя отозвать)."""
    with get_client() as client:
        r = client.delete(f"/auth/tokens/{token_id}")
        r.raise_for_status()
    console.print(f"[red]Токен отозван:[/red] {token_id}")


@token.command("whoami")
def token_whoami():
    """Информация о текущем токене."""
    with get_client() as client:
        r = client.get("/auth/whoami")
        r.raise_for_status()
    data = r.json()
    console.print(f"Роль: [cyan]{data.get('role')}[/cyan]")
    console.print(f"ID: {data.get('token_id')}")
    console.print(f"Описание: {data.get('description', '-')}")


# ── delete ────────────────────────────────────────────────────────────────

@cli.group()
def delete():
    """Удалить ресурсы из кластера."""


@delete.command("worker")
@click.argument("worker_id")
@click.option("--yes", is_flag=True, help="Пропустить подтверждение")
def delete_worker(worker_id, yes):
    """Удалить воркер из кластера (только admin)."""
    if not yes:
        click.confirm(f"Удалить воркер '{worker_id}' из кластера?", abort=True)
    with get_client() as client:
        r = client.delete(f"/workers/{worker_id}")
        r.raise_for_status()
    console.print(f"[red]Воркер удалён:[/red] {worker_id}")


# ── task ─────────────────────────────────────────────────────────────────

@cli.group()
def task():
    """Управление задачами кластера."""


@task.command("clear")
@click.option("--yes", is_flag=True, help="Пропустить подтверждение")
def task_clear(yes):
    """Удалить всю историю задач (только admin)."""
    if not yes:
        click.confirm("Удалить всю историю задач? Это действие необратимо.", abort=True)
    with get_client() as client:
        r = client.delete("/tasks")
        r.raise_for_status()
    console.print("[red]История задач очищена.[/red]")


# ── misc ──────────────────────────────────────────────────────────────────

@cli.command("who-master")
def who_master():
    """Показать текущего лидера кворума."""
    with get_client() as client:
        r = client.get("/who_master")
        r.raise_for_status()
    data = r.json()
    marker = "[bold green]ЛИДЕР[/bold green]" if data.get("is_master") else "ведомый"
    console.print(f"Узел [cyan]{data['node_id']}[/cyan] → {marker}")
    console.print(f"Кворум: {data.get('quorum_state')} (ft={data.get('fault_tolerance', 0)})")
    if data.get("warning"):
        console.print(f"[yellow]Предупреждение:[/yellow] {data['warning']}")


@cli.command("quorum")
def quorum_cmd():
    """Показать статус кворума кластера."""
    with get_client() as client:
        r = client.get("/quorum")
        r.raise_for_status()
    data = r.json()
    state_color = "green" if data.get("quorum_ok") else "red"
    console.print(f"Мастер-узлов: [bold]{data.get('master_count')}[/bold]")
    console.print(f"Состояние: [{state_color}]{data.get('quorum_state')}[/{state_color}]")
    console.print(f"Отказоустойчивость: {data.get('fault_tolerance', 0)} узел(-ов)")
    if data.get("warning"):
        console.print(f"[yellow]⚠ {data['warning']}[/yellow]")


@cli.command("health")
def health():
    """Проверить состояние кластера."""
    with get_client() as client:
        r = client.get("/health")
        r.raise_for_status()
    data = r.json()
    rprint(data)
    qstate = data.get("quorum_state", "unknown")
    qok = data.get("quorum_ok", False)
    color = "green" if qok else "red"
    console.print(f"Кворум: [{color}]{qstate}[/{color}]")
    if data.get("quorum_warning"):
        console.print(f"[yellow]⚠ {data['quorum_warning']}[/yellow]")


if __name__ == "__main__":
    cli()
