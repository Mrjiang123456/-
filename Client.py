import socket
import threading
import sounddevice as sd
import numpy as np
import logging
import time
# from bullying import device_name, school_name

# 设置日志记录器
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ClientLogger")

# 定义一个事件，当它设置时，其他线程将停止它们的活动
operation_event = threading.Event()

device_name = ''  # 自行定义设备名
school_name = ''  # 自行定义学校名


class Client:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.target_ip = '0.0.0.0'  # 修改成你服务器ip
        self.target_port = 9000  # 修改成你服务器端口

        while True:
            try:
                self.s.connect((self.target_ip, self.target_port))
                break
            except Exception as e:
                logger.error("Couldn't connect to server: %s", e)
                print("Couldn't connect to server")

        self.chunk_size = 1024  # 数据切片大小
        self.channels = 1  # 声道数
        self.rate = 16000  # 采样率

        logger.info("Connected to Server")
        print("Connected to Server")

        # 发送 device_name 和 school_name
        try:
            self.s.sendall(f"{device_name}:{school_name}".encode('utf-8'))
            logger.info(f"Sent device info: {device_name}, {school_name}")
            print(f"Sent device info: {device_name}, {school_name}")
        except Exception as e:
            logger.error("Couldn't send device info: %s", e)
            print("Couldn't send device info: %s" % e)

        # 标记通话状态
        self.in_call = True
        self.start_time = time.time()

        # 启动线程
        self.receive_thread = threading.Thread(target=self.receive_server_data)
        self.receive_thread.start()
        self.send_thread = threading.Thread(target=self.send_data_to_server)
        self.send_thread.start()

    def receive_server_data(self):
        accumulated_data = b''
        with sd.OutputStream(samplerate=self.rate, channels=self.channels, blocksize=self.chunk_size,
                             dtype='int16') as stream:
            while self.in_call:
                try:
                    data = self.s.recv(1024)
                    if not data:
                        logger.info("Connection closed by server.")
                        print("Connection closed by server.")
                        self.stop_call()
                        break
                    self.start_time = time.time()  # 更新计时器
                    accumulated_data += data
                    if b'aaaaaa123456:end' in accumulated_data:
                        logger.info("Received end signal, closing connection.")
                        print("Received end signal, closing connection.")
                        self.stop_call()
                        break
                    while len(accumulated_data) >= 1024:
                        chunk, accumulated_data = accumulated_data[:1024], accumulated_data[1024:]
                        self.play_audio(chunk, stream)
                    # else:
                    #     logger.info("Connection closed by server.")
                    #     print("Connection closed by server.")
                    #     self.stop_call()
                    #     break
                except Exception as e:
                    logger.error("Exception in receive_server_data: %s", e)
                    print("Exception in receive_server_data: %s" % e)
                    self.stop_call()
                    break
        logger.info("receive_server_data 线程结束")
        print("receive_server_data 线程结束")

    def send_data_to_server(self):
        with sd.InputStream(samplerate=self.rate, channels=self.channels, blocksize=self.chunk_size,
                            dtype='int16') as stream:
            while self.in_call:
                try:
                    data, _ = stream.read(self.chunk_size)
                    if not data.any():
                        logger.info("No data to send, closing connection.")
                        print("No data to send, closing connection.")
                        self.stop_call()
                        break
                    self.s.sendall(data.tobytes())
                    if time.time() - self.start_time > 40:
                        logger.info("No connection established within 40 seconds, closing connection.")
                        print("No connection established within 40 seconds, closing connection.")
                        self.stop_call()
                        break
                except Exception as e:
                    logger.error("Exception in send_data_to_server: %s", e)
                    print("Exception in send_data_to_server: %s" % e)
                    self.stop_call()
                    break
        logger.info("send_data_to_server 线程结束")
        print("send_data_to_server 线程结束")

    def play_audio(self, data, stream):
        data = np.frombuffer(data, dtype=np.int16)
        stream.write(data)

    def stop_call(self):
        self.in_call = False
        logger.info("Stopping call...")
        print("Stopping call...")

        # 关闭socket连接
        try:
            self.s.shutdown(socket.SHUT_RDWR)
            self.s.close()
            print("socket关闭")
        except Exception as e:
            logger.error("Exception on socket shutdown/close: %s", e)
            print("Exception on socket shutdown/close: %s" % e)

        operation_event.set()
        logger.info("Call stopped and connection closed.")
        print("Call stopped and connection closed.")


if __name__ == '__main__':
    client = Client()
