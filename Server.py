import socket
import threading
from concurrent.futures import ThreadPoolExecutor
import time


class ForwardingThread(threading.Thread):
    def __init__(self, school_name, raspberry_pi_conn, android_conn, timeout=60):
        super().__init__()
        self.school_name = school_name
        self.raspberry_pi_conn = raspberry_pi_conn
        self.android_conn = android_conn
        self.connections = raspberry_pi_conn + android_conn
        self.running = True
        self.timeout = timeout
        self.last_activity_time = time.time()

    def run(self):
        while self.running:
            for conn in self.connections:
                try:
                    data = conn.recv(1024)
                    if data:
                        self.broadcast(conn, data)
                        self.last_activity_time = time.time()
                    else:
                        self.remove_connection(conn)
                except:
                    self.remove_connection(conn)

    def broadcast(self, sender_socket, data):
        for conn in self.connections:
            if conn != sender_socket:
                try:
                    conn.sendall(data)
                except:
                    self.remove_connection(conn)

    def remove_connection(self, conn):
        if conn in self.connections:
            self.connections.remove(conn)
            conn.close()

    def stop(self):
        self.running = False
        for conn in self.connections:
            conn.close()

    def check_timeout(self):
        return time.time() - self.last_activity_time > self.timeout


class Server:
    def __init__(self):
        self.ip = socket.gethostbyname(socket.gethostname())
        self.port = 9000  # 设置端口为0，系统将自动分配一个可用端口
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 启用SO_REUSEADDR选项
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.executor = ThreadPoolExecutor(max_workers=10)  # 创建线程池，设置最大工作线程数

        try:
            self.s.bind(('0.0.0.0', self.port))
            self.port = self.s.getsockname()[1]  # 获取系统分配的端口
            self.connections = []

            self.raspberry_pi_connection = []  # 树莓派端的socket列表
            self.android_connection = []  # Android端的socket列表
            self.clients = {}  # 存储学校与设备信息的字典
            self.forwarding_threads = {}  # 存储学校与通话转发线程的字典

            # 启动监听线程
            # threading.Thread(target=self.listen_for_connections, args=(self.raspberry_pi_connection, 9001)).start()
            # threading.Thread(target=self.listen_for_connections, args=(self.android_connection, 9002)).start()

            # 启动超时检查线程
            threading.Thread(target=self.check_for_timeouts).start()

            print('Running on IP:' + self.ip)
            print('Running on port:' + str(self.port))

            self.accept_connections()
        except Exception as e:
            print("Error binding to port: ", e)
            return

    def close_socket(self, sock, conn_list):
        if sock:
            sock.close()
        if sock in conn_list:
            conn_list.remove(sock)
        if sock in self.connections:
            self.connections.remove(sock)
            # 从 clients 字典中删除相关条目
            for school_name, info in list(self.clients.items()):
                if info['socket'] == sock:
                    del self.clients[school_name]
                    break

    def accept_connections(self):
        self.s.listen(100)
        # print('Running on IP: ' + self.ip)
        # print('Running on port: ' + str(self.port))

        while True:
            try:
                client_socket, addr = self.s.accept()
                self.connections.append(client_socket)
                # 提交任务到线程池
                self.executor.submit(self.handle_client, client_socket, addr)
            except Exception as e:
                print(f"Accept connection error: {e}")

    def broadcast(self, sender_socket, data):
        for client in self.connections:
            if client != sender_socket:
                try:
                    client.sendall(data)
                except Exception as e:
                    print(f"Broadcast error: {e}")
                    self.close_socket(client, self.connections)

    def handle_client(self, client_socket, addr):
        # print(f"New connection from {addr}")
        # try:
        #     while True:
        #         try:
        #             data = client_socket.recv(1024)
        #             # print(data)
        #             if not data:
        #                 print(f"Connection from {addr} closed by client.")
        #                 break
        #                 # 当接收到结束信号时，只需检查一次
        #             if data.endswith(b'aaaaaa123456:end'):
        #                 print(f"Connection from {addr} sent end signal. Closing connection.")
        #                 self.broadcast(client_socket, b'aaaaaa123456:end')
        #                 break  # 结束当前连接的循环
        #             else:
        #                 self.broadcast(client_socket, data)  # 正常广播收到的数据
        #         except (ConnectionResetError, BrokenPipeError):
        #             print(f"Connection from {addr} was reset by peer.")
        #             break
        # except Exception as e:
        #     print(f"Unexpected error: {e}")
        # finally:
        #     self.close_socket(client_socket, self.connections)  # 关闭socket并从连接列表中移除
        #     print(f"Connection from {addr} has been closed.")

        print(f"New connection from {addr}")
        try:
            device_info = client_socket.recv(1024).decode('utf-8')
            if ':' in device_info:  # 树莓派端
                device_name, school_name = device_info.split(':')
                if school_name not in self.clients:
                    self.clients[school_name] = {'raspberry_pi': [client_socket], 'android': []}
                else:
                    self.clients[school_name]['raspberry_pi'].append(client_socket)
                self.raspberry_pi_connection.append(client_socket)
                print(f"Device :{device_name} from school :{school_name} connected on port :{self.port}.")
            else:  # 安卓端
                school_name = device_info
                if school_name not in self.clients:
                    self.clients[school_name] = {'raspberry_pi': [], 'android': [client_socket]}
                else:
                    self.clients[school_name]['android'].append(client_socket)
                self.android_connection.append(client_socket)
                print(f"Android client from school :{school_name} connected on port :{self.port}.")

            if school_name in self.forwarding_threads:
                self.forwarding_threads[school_name].connections.append(client_socket)
            else:
                self.forwarding_threads[school_name] = ForwardingThread(
                    school_name,
                    self.clients[school_name]['raspberry_pi'],
                    self.clients[school_name]['android']
                )
                self.forwarding_threads[school_name].start()

            while True:
                try:
                    data = client_socket.recv(1024)
                    if not data:
                        print(f"Connection from {addr} closed by client.")
                        break
                    if data.endswith(b'aaaaaa123456:end'):
                        print(f"Connection from {addr} sent end signal. Closing connection.")
                        self.broadcast(client_socket, b'aaaaaa123456:end')
                        break  # 结束当前连接的循环
                    else:
                        self.broadcast(client_socket, data)  # 正常广播收到的数据
                except (ConnectionResetError, BrokenPipeError):
                    print(f"Connection from {addr} was reset by peer.")
                    break
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.close_socket(client_socket, self.connections)  # 关闭socket并从连接列表中移除
            print(f"Connection from {addr} has been closed.")

    # def listen_for_connections(self, conn_list, port):
    #     listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #
    #     try:
    #         listen_socket.bind(('0.0.0.0', port))
    #         listen_socket.listen(1)
    #         print(f"Listening for connections on port {port}")
    #
    #         while True:
    #             client_socket, addr = listen_socket.accept()
    #             conn_list.append(client_socket)
    #             print(f"New connection from {addr} on port {port}")
    #             threading.Thread(target=self.handle_specific_connection, args=(client_socket, conn_list, port)).start()
    #     except Exception as e:
    #         print(f"Error listening for connections on port {port}: {e}")
    #     finally:
    #         listen_socket.close()

    # def handle_specific_connection(self, client_socket, conn_list, port):
    #     try:
    #         if port == 9001:  # 树莓派端
    #             device_info = client_socket.recv(1024).decode('utf-8')
    #             device_name, school_name = device_info.split(':')
    #             if school_name not in self.clients:
    #                 self.clients[school_name] = {'raspberry_pi': [client_socket], 'android': []}
    #             else:
    #                 self.clients[school_name]['raspberry_pi'].append(client_socket)
    #             print(f"Device :{device_name} from school :{school_name} connected on port :{port}.")
    #         elif port == 9002:  # 安卓端
    #             school_name = client_socket.recv(1024).decode('utf-8')
    #             if school_name not in self.clients:
    #                 self.clients[school_name] = {'raspberry_pi': [], 'android': [client_socket]}
    #             else:
    #                 self.clients[school_name]['android'].append(client_socket)
    #             print(f"Android client from school :{school_name} connected on port :{port}.")
    #
    #         if school_name in self.forwarding_threads:
    #             self.forwarding_threads[school_name].connections.append(client_socket)
    #         else:
    #             self.forwarding_threads[school_name] = ForwardingThread(
    #                 school_name,
    #                 self.clients[school_name]['raspberry_pi'],
    #                 self.clients[school_name]['android']
    #             )
    #             self.forwarding_threads[school_name].start()
    #
    #     except Exception as e:
    #         print(f"Error handling connection on port {port}: {e}")
    #     finally:
    #         self.close_socket(client_socket, conn_list)
    #         print(f"{device_name}:Connection on port {port} closed.")

    def check_for_timeouts(self):
        while True:
            time.sleep(10)  # 每10秒检查一次
            for school_name, thread in list(self.forwarding_threads.items()):
                if thread.check_timeout():
                    print(f"Forwarding thread for school {school_name} timed out. Stopping thread.")
                    thread.stop()
                    del self.forwarding_threads[school_name]


# 服务器初始化并运行
if __name__ == "__main__":
    server = Server()
