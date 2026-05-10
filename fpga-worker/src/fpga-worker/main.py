# ============ ENTITIES (Domain Layer) ============

from enum import Enum


class FPGAStatus(Enum):
    IDLE = "простаивает"
    LOADED = "загружена"


class InterfacePort:
    """Абстракция интерфейса — порт подключения."""
    def send(self, data: str):
        raise NotImplementedError

    def port_id(self) -> str:
        raise NotImplementedError


class FPGA:
    """Доменная сущность FPGA."""
    def __init__(self, port: InterfacePort):
        self.port = port
        self.status = FPGAStatus.IDLE
        self.project_data = None

    def load_project(self, data: str):
        self.project_data = data
        self.status = FPGAStatus.LOADED


# ============ PORTS (Use Case Interfaces) ============

# Входные порты (input ports)
class GetProjectUseCase:
    def execute(self, project_path: str, token: str) -> str:
        raise NotImplementedError


class UploadProjectUseCase:
    def execute(self, fpga: FPGA, project_data: str):
        raise NotImplementedError


# Выходной порт фабрики интерфейсов
class InterfaceFactoryPort:
    def create_usb(self) -> InterfacePort:
        raise NotImplementedError
    
    def create_ethernet(self) -> InterfacePort:
        raise NotImplementedError


# ============ USE CASES (Interactors) ============

class GetProjectInteractor(GetProjectUseCase):
    def execute(self, project_path: str, token: str) -> str:
        # Заглушка: читаем txt
        with open(project_path, "r", encoding="utf-8") as f:
            return f.read()


class UploadProjectInteractor(UploadProjectUseCase):
    def execute(self, fpga: FPGA, project_data: str):
        fpga.load_project(project_data)
        # Выводим содержимое проекта
        print("=== Содержимое проекта ===")
        print(project_data)
        print("==========================")
        # Вызываем порт FPGA
        print(f"[Интерфейс FPGA] Используется порт: {fpga.port.port_id()}")


# ============ ADAPTERS (Infrastructure) ============

class USBPortAdapter(InterfacePort):
    def __init__(self, port_id: str):
        self._id = port_id

    def send(self, data: str):
        print(f"[USB] Отправлено: {data}")

    def port_id(self) -> str:
        return f"USB:{self._id}"


class EthernetPortAdapter(InterfacePort):
    def __init__(self, port_id: str):
        self._id = port_id

    def send(self, data: str):
        print(f"[Ethernet] Отправлено: {data}")

    def port_id(self) -> str:
        return f"ETH:{self._id}"


# ============ Interface Factory ============

class InterfaceFactory(InterfaceFactoryPort):
    def create_usb(self) -> InterfacePort:
        return USBPortAdapter("001")

    def create_ethernet(self) -> InterfacePort:
        return EthernetPortAdapter("A12")


# ============ INPUT ADAPTER (Controller) ============

class ConsoleController:
    def __init__(self, get_uc: GetProjectUseCase, upload_uc: UploadProjectUseCase,
                 factory: InterfaceFactoryPort):
        self.get_uc = get_uc
        self.upload_uc = upload_uc
        self.factory = factory

    def run_demo(self, project_path: str):
        # 1. Создаём два интерфейса
        usb = self.factory.create_usb()
        eth = self.factory.create_ethernet()

        # 2. Создаём две FPGA
        fpga1 = FPGA(usb)
        fpga2 = FPGA(eth)

        print(f"FPGA1 статус: {fpga1.status.value}")
        print(f"FPGA2 статус: {fpga2.status.value}")

        # 3. Читаем проект
        project_data = self.get_uc.execute(project_path, token="")

        # 4. Загружаем проект на FPGA1
        print("\nЗагружаем проект в FPGA1...\n")
        self.upload_uc.execute(fpga1, project_data)

        print(f"FPGA1 статус: {fpga1.status.value}")


# ============ MAIN (Composition Root) ============

def main():
    get_uc = GetProjectInteractor()
    upload_uc = UploadProjectInteractor()
    factory = InterfaceFactory()

    controller = ConsoleController(get_uc, upload_uc, factory)
    controller.run_demo("project.txt")


if __name__ == "__main__":
    main()
