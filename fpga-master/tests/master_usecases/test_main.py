import pytest
import requests

BASE_URL = "http://0.0.0.0:3030"


def test_queue_operations():
    # Проверяем, что очередь изначально пуста
    response = requests.get(f"{BASE_URL}/get_queue")
    assert response.status_code == 200
    assert response.json() == {"queue": []}

    # Добавляем проекты
    projects = [
        {"project_id": "1", "project_name": "counter-7segments", "sources_url": "http://my-minio.local/counter-7segments", "pipiline_id": "12e12edqwdd2312e12"},
        {"project_id": "2", "project_name": "fsm-7segments", "sources_url": "http://my-minio.local/fsm-7segments", "pipiline_id": "5678asfwq3213r"}
    ]
    for project in projects:
        response = requests.post(f"{BASE_URL}/put_project", json=project)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    # Проверяем, что оба проекта в очереди
    response = requests.get(f"{BASE_URL}/get_queue")
    assert response.status_code == 200
    queue = response.json()["queue"]
    for project in projects:
        assert any(p["project_id"] == project["project_id"] for p in queue)

    # Пробуем удалить несуществующий проект
    response = requests.post(f"{BASE_URL}/remove_project", json={"project_id": "999"})
    assert response.status_code == 200
    result = response.json()
    assert result["removed"] is False
    assert result["project"] is None

    # Удаляем существующий проект
    response = requests.post(f"{BASE_URL}/remove_project", json={"project_id": "1"})
    assert response.status_code == 200
    result = response.json()
    assert result["removed"] is True
    assert result["project"]["project_id"] == "1"

    # Проверяем очередь после удаления
    response = requests.get(f"{BASE_URL}/get_queue")
    queue = response.json()["queue"]
    assert all(p["project_id"] != "1" for p in queue)
    assert any(p["project_id"] == "2" for p in queue)
    
    # Удаляем последний существующий проект
    response = requests.post(f"{BASE_URL}/remove_project", json={"project_id": "2"})
    assert response.status_code == 200
    result = response.json()
    assert result["removed"] is True
    assert result["project"]["project_id"] == "2"


def test_master_status():
    # Проверяем статус текущего мастера
    response = requests.get(f"{BASE_URL}/who_master")
    assert response.status_code == 200
    data = response.json()
    assert "is_master" in data
    assert "node_id" in data

    # Проверяем список всех мастеров
    response = requests.get(f"{BASE_URL}/get_masters")
    assert response.status_code == 200
    masters = response.json()
    assert isinstance(masters, list)
    for master in masters:
        assert "node_id" in master
        assert "standalone" in master
