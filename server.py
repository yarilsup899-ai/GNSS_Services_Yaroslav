import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server_adress = ("localhost", 8888)
server_socket.bind(server_adress)

server_socket.listen(1)
print(f"Сервер запущен на {server_adress}")

while True:
    client_socket, client_adress = server_socket.accept()
    print(f"Подключен клиент {client_adress}")

    try:
        data = client_socket.recv(1024)

        if data:
            print(f"Получено: {data.decode('utf-8')}")
            response = "Привет от сервера!"
            client_socket.sendall(response.encode('utf-8'))

    finally:
        client_socket.close()