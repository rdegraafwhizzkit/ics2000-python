import enum
import requests
import json
import ast
import logging
import socket
import time

from ics2000_python.Cryptographer import decrypt
from ics2000_python.Command import Command
from ics2000_python.Devices import Device, Light, Dimmer, Optional, TemperatureHumiditySensor

_LOGGER = logging.getLogger(__name__)


def constraint_int(inp, min_val, max_val) -> int:
    if inp < min_val:
        return min_val
    elif inp > max_val:
        return max_val
    else:
        return inp


class CoreException(Exception):
    pass


class Hub:
    aes = None
    mac = None
    base_url = "https://trustsmartcloud2.com/ics2000_api/"

    def __init__(self, mac, email, password):
        """Initialize an ICS2000 hub."""
        self.mac = mac
        self._email = email
        self._password = password
        self._connected = False
        self._homeId = -1
        self._devices = []
        self.login_user()
        self.pull_devices()
        self.ip_address = get_hub_ip()

    def login_user(self):
        _LOGGER.debug("Logging in user")
        url = f'{Hub.base_url}/account.php'
        params = {"action": "login", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "device_unique_id": "android", "platform": "Android"}
        req = requests.get(url, params=params)
        if req.status_code == 200:
            resp = req.json()
            self.aes = resp["homes"][0]["aes_key"]
            self._homeId = resp["homes"][0]["home_id"]
            if self.aes is not None:
                _LOGGER.debug("Successfully got AES key")
                self._connected = True
            else:
                raise CoreException(f'Could not get AES key for user {self._email}')
        else:
            raise CoreException(f'Could not login user {self._email}')

    @property
    def connected(self):
        return self._connected

    def pull_devices(self):
        device_type_values = [item.value for item in DeviceType]
        url = f'{Hub.base_url}/gateway.php'
        params = {
            "action": "sync", "email": self._email,
            "mac": self.mac.replace(":", ""), "password_hash": self._password,
            "home_id": self._homeId
        }
        resp = requests.get(url, params=params)
        self._devices = []

        for device in resp.json():

            data = json.loads(decrypt(device["data"], self.aes))

            if 'module' in data and 'info' in data['module']:

                name = data['module']['name']
                entity_id = data['module']['id']
                device_type = data['module']['device']

                if device_type not in device_type_values:
                    self._devices.append(Device(name, entity_id, self))
                    continue

                dev = DeviceType(device_type)
                logging.debug(f'Device type is {device_type}')

                self._devices.append(
                    {
                        DeviceType.LAMP: Light,  # 1
                        DeviceType.DIMMER: Dimmer,  # 2
                        DeviceType.OPEN_CLOSE: Light,  # 3
                        DeviceType.ZIGBEE: Light, # 12
                        DeviceType.DIMMABLE_LAMP: Dimmer,  # 24
                        DeviceType.KAKUSCHAKELAAR: Light, # 41
                        DeviceType.ZIGBEE_TEMPERATURE_AND_HUMIDITY_SENSOR: TemperatureHumiditySensor  # 46
                    }[dev](name, entity_id, self)
                )
            else:
                pass  # TODO: log something here

    @property
    def devices(self):
        return self._devices

    def send_command_tcp(self, command):
        url = f'{Hub.base_url}/command.php'
        _LOGGER.info(f'Using TCP to send command to {url}')
        params = {"action": "add", "email": self._email, "mac": self.mac.replace(":", ""),
                  "password_hash": self._password, "device_unique_id": "android", "command": command}
        response = requests.get(url, params=params)
        if 200 != response.status_code:
            raise CoreException(f'Could not send command {command}: {response.text}')

    def send_command_udp(self, command):
        _LOGGER.info(f'Using UDP to send command to {self.ip_address}')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(command, (self.ip_address, 2012))
        sock.close()

    def turn_off(self, entity):
        cmd = self.simple_command(entity, 0, 0)
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def turn_on(self, entity):
        cmd = self.simple_command(entity, 0, 1)
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def dim(self, entity, level):
        # level is in range 1-10
        cmd = self.simple_command(entity, 1, level)
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def zigbee_color_temp(self, entity, color_temp):
        color_temp = constraint_int(color_temp, 0, 600)
        cmd = self.simple_command(entity, 9, color_temp)
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def zigbee_dim(self, entity, dim_lvl):
        dim_lvl = constraint_int(dim_lvl, 1, 254)
        cmd = self.simple_command(entity, 4, dim_lvl)
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def zigbee_switch(self, entity, power):
        cmd = self.simple_command(entity, 3, (str(1) if power else str(0)))
        if self.ip_address:
            self.send_command_udp(cmd.getcommandbytes())
        else:
            self.send_command_tcp(cmd.getcommand())

    def get_device_status(self, entity) -> []:
        url = f'{Hub.base_url}/entity.php'
        params = {
            "action": "get-multiple",
            "email": self._email,
            "mac": self.mac.replace(":", ""),
            "password_hash": self._password,
            "home_id": self._homeId,
            "entity_id": f'[{str(entity)}]'
        }
        arr = requests.get(url, params=params).json()
        if len(arr) == 1 and "status" in arr[0] and arr[0]["status"] is not None:
            obj = arr[0]
            status = json.loads(decrypt(obj["status"], self.aes))
            if "module" in status and "functions" in status["module"]:
                return status["module"]["functions"]
        return []

    def get_lamp_status(self, entity) -> Optional[bool]:
        status = self.get_device_status(entity)
        if len(status) >= 1:
            return True if status[0] == 1 else False
        return False

    def get_temperature(self, entity):
        status = self.get_device_status(entity)
        if len(status) >= 1:
            return round(status[4] / 100.0, 2)
        return -1

    def get_humidity(self, entity):
        status = self.get_device_status(entity)
        if len(status) >= 1:
            return round(status[11] / 100.0, 2)
        return -1

    def simple_command(self, entity, function, value):
        cmd = Command()
        cmd.setmac(self.mac)
        cmd.settype(128)
        cmd.setmagic()
        cmd.setentityid(entity)
        cmd.setdata(
            json.dumps({'module': {'id': entity, 'function': function, 'value': value}}, separators=(',', ':')),
            self.aes
        )
        return cmd


class DeviceType(enum.Enum):
    LAMP = 1
    DIMMER = 2
    OPEN_CLOSE = 3
    ZIGBEE = 12
    DIMMABLE_LAMP = 24
    KAKUSCHAKELAAR = 41
    ZIGBEE_TEMPERATURE_AND_HUMIDITY_SENSOR = 46


def get_hub(mac, email, password) -> Optional[Hub]:
    url = f'{Hub.base_url}/gateway.php'
    params = {"action": "check", "email": email, "mac": mac.replace(":", ""), "password_hash": password}
    resp = requests.get(url, params=params)
    if resp.status_code == 200:
        if ast.literal_eval(resp.text)[1] == "true":
            return Hub(mac, email, password)
    raise CoreException(f'Could not create a Hub object for mac/user {mac}/{email}')


def get_hub_ip(timeout: int = 10) -> str:
    msg = bytes.fromhex('010003ffffffffffffca000000010400044795000401040004000400040000000000000000020000003000')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(msg, ('255.255.255.255', 2012))
    sock.setblocking(False)
    ip_address = None
    end_at = int(time.time()) + timeout
    while not ip_address and int(time.time()) < end_at:
        try:
            _, addr = sock.recvfrom(1024)
            ip_address = addr[0]
        except BlockingIOError:
            pass
    sock.close()

    return ip_address
