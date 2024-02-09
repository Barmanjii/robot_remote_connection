# Python Imports
import os
import json
import asyncio
import logging
import subprocess
from threading import Thread, Event

# PyYaml Import
import yaml

# Websockets Import
import websockets

# ZMQ Import
import zmq

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)
event = Event()


class RobotRemoteConnection:
    def __init__(self) -> None:
        self.machine_id = None
        self.process = "webtty_v1.1"
        self.host_token = None
        self.client_token = None
        self.base_url = "ws://192.168.0.104:2323/ws"
        self.zmq_url = "tcp://localhost:5555"
        self.host_token_sent = False
        self.process_start = False
        self.client_token_sent = False

    # Fetch from the robot
    def get_machine_id(self):
        """Get the Machine Id from the robot local storage.
        """
        machine_info_path = os.path.join(
            os.getenv("HOME"), ".machineinfo.yaml")
        try:
            with open(machine_info_path, "r") as file:
                data = yaml.safe_load(file)
                self.machine_id = data.get('MACHINEID', 'Unknown')
        except FileNotFoundError:
            print(f"The file {machine_info_path} does not exist.")
        except Exception as e:
            logger.error(f"Exception while reading the file - {str(e)}")

    async def send_message(self):
        """
        Established the WebSocket connection and ZMQ Connection, Run both on a different Thread as they are I/O blocking.
        """
        zmq_thread = Thread(target=self.zmq_client)
        zmq_thread.start()

        # Get the Machine ID
        self.get_machine_id()
        async with websockets.connect(self.base_url) as websocket:
            await websocket.send(json.dumps({"connection_type": 1, "machine_id": self.machine_id}))
            while True:
                try:
                    response = await websocket.recv()
                    json_response_server = json.loads(response)

                    # logger.info(f"Received from server: {response}")
                    if not self.process_start:
                        self.start_the_thread(process=self.process)
                        self.process_start = True

                    if 'client_token' in json_response_server:
                        self.client_token = json_response_server['client_token']
                        logger.info("Client Token Received from the Server")

                    event.wait()
                    if not self.host_token_sent:
                        await self.sent_data_to_server(websocket=websocket)

                except websockets.ConnectionClosedError as e:
                    logger.error(str(e))
                    break  # Exit loop on connection error

    async def sent_data_to_server(self, websocket):
        """
        Sent the Host Token to Backend Server
        """
        try:
            await websocket.send(json.dumps({"connection_type": 1,  "machine_id": self.machine_id, "host_token": self.host_token}))
            self.host_token_sent = True
        except Exception as e:
            logger.error(
                f"Exception while sending the data to server - {str(e)}")

    def start_the_thread(self, process: str):
        """Run the WebTTY on a different Thread.

        Args:
            process (str): Process name : WebTTYv1.1
        """
        try:
            process_thread = Thread(
                target=lambda: subprocess.Popen(process.split()))
            process_thread.start()
            logger.info("Started the Thread")

        except Exception as e:
            logger.error(str(e))

    def zmq_client(self):
        """
        ZMQ Client function to communicate with the Webtty-ZMQ server
        """
        context = zmq.Context()
        zmq_socket = context.socket(zmq.PAIR)
        zmq_socket.connect(self.zmq_url)
        logger.info("Waiting for the ZMQ Server to connect.......")
        try:
            while True:
                response = zmq_socket.recv_string()
                self.host_token = response
                event.set()
                while True:
                    if self.client_token is not None:
                        zmq_socket.send_string(json.dumps(
                            {"Client_Token": self.client_token}))
                        break
        except Exception as e:
            logger.error(str(e))


if __name__ == "__main__":
    remote_connection = RobotRemoteConnection()
    asyncio.run(remote_connection.send_message())
