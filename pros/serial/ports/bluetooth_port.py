# code for a bluetooth port!

import sys
import time
import os
import simplepyble

from typing import *

from pros.common import dont_send, logger
from pros.serial.ports.exceptions import ConnectionRefusedException, PortNotFoundException
from .base_port import BasePort, PortConnectionException

# set our max packet size
MAX_PACKET_SIZE = 244

V5_ID = "VEX_V5"

class BluetoothPort(BasePort):
    def __init__(self, port_name: str, **kwargs):
        # define our BLE UUIDs
        self.service_uuid = "08590f7e-db05-467e-8757-72f6faeb13d5"
        self.data_tx_uuid = "08590f7e-db05-467e-8757-72f6faeb1306"
        self.data_rx_uuid = "08590f7e-db05-467e-8757-72f6faeb13f5"
        self.user_tx_uuid = "08590f7e-db05-467e-8757-72f6faeb1316"
        self.user_rx_uuid = "08590f7e-db05-467e-8757-72f6faeb1326"
        self.pairing_uuid = "08590f7e-db05-467e-8757-72f6faeb13e5"

        # devices paired
        self.devices = []

        #logger(__name__).debug(f'Opening bluetooth port {port_name}')
        print('[BETA] - Using Bluetooth!')

        adapters = simplepyble.Adapter.get_adapters()

        if len (adapters) == 0:
            raise dont_send(Exception('Bluetooth adapter not found'))
        
        self.adapter = adapters[0]

        print('Scanning for devices...')

        self.adapter.set_callback_on_scan_found(self.got_device_cb)
        self.adapter.scan_start()

        print("Scanning...", end="")
        while len(self.devices) == 0:
            time.sleep(0.5)
            print(".", end="", flush=True)
        print("")

        self.adapter.scan_stop()
        peripherals = self.adapter.scan_get_results()

        # filter out non-V5 devices
        peripherals = [p for p in peripherals if V5_ID in p.identifier()]

        # sort by signal strength if we have multiple devices
        peripherals = sorted(peripherals, key=lambda p: p.rssi())

        if len(peripherals) == 0:
            raise dont_send(Exception('No V5 devices found'))

        # connect to the first device
        self.peripheral = peripherals[0]
        self.peripheral.connect()

        magic = self.peripheral.read(self.service_uuid, self.pairing_uuid)
        if int.from_bytes(magic, 'big') != 0xdeadface:
            raise dont_send(Exception('Invalid magic number! Are you sure this is a V5 device?'))
        
        # enter pairing mode
        self.peripheral.write_request(self.service_uuid, self.pairing_uuid, bytes([0xff, 0xff, 0xff, 0xff]))

        # get user input
        print('Pairing Code:', end="")
        code = input()

        # remove spaces, dashes, and colons (why there would be dashes or colons in a pairing code is beyond me)
        code = code.replace(" ", "").replace("-", "").replace(":", "")

        # convert to bytes
        code = bytes(int(c) for c in code)

        # send the pairing code
        self.peripheral.write_request(self.service_uuid, self.pairing_uuid, code)

        # grab response and wait for pairing to complete
        print ('Pairing...', end="")
        cresp = bytes([])
        while cresp != code:
            cresp = self.peripheral.read(self.service_uuid, self.pairing_uuid)
            time.sleep(0.5)
            print(".", end="", flush=True)

        print("")

        self.peripheral.notify(self.service_uuid, self.data_tx_uuid, self.handle_notification)
        self.buffer: bytearray = bytearray()

    def got_device_cb(self, peripheral):
        # check if our device is a V5
        if V5_ID in peripheral.identifier():
            print(f'Found V5 device: {peripheral.identifier()}')
            self.devices.append(peripheral)

    def handle_notification(self, data):
        self.buffer.extend(data)

    def read(self, n_bytes: int = 0) -> bytes:
        if n_bytes <= 0:
            msg = bytes(self.buffer)
            self.buffer = bytearray()
            return msg
        else:
            if len(self.buffer) < n_bytes:
                msg = bytes(self.buffer)
                self.buffer = bytearray()
            else:
                msg, self.buffer = bytes(self.buffer[:n_bytes]), self.buffer[n_bytes:]
            return msg
        
    def write(self, data: Union[str, bytes]):
        # for line in traceback.format_stack():
        #     print(line.strip())
        if isinstance(data, str):
            data = data.encode(encoding='ascii')
        else:
            data = bytes(data)
        for i in range(0, len(data), MAX_PACKET_SIZE):
            # print(len(data[i:min(len(data), i+MAX_PACKET_SIZE)]))
            self.peripheral.write_command(self.UUIDs["SERVICE"], self.UUIDs["DATA_RX"], data[i:min(len(data), i+MAX_PACKET_SIZE)])
            # time.sleep(0.3)
        # self.peripheral.write_command(self.UUIDs["SERVICE"], self.UUIDs["DATA_RX"], bytes([0x00]))

    def destroy(self):
        logger(__name__).debug(f'Destroying {self.__class__.__name__} to {self.serial.name}')
        self.peripheral.disconnect()

    @property
    def name(self) -> str:
        return self.serial.portstr

    def __str__(self):
        return str("Bluetooth Port")