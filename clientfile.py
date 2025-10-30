import socket # позволяет осущ подключение между клиентской и и серверной подключение порта 
import struct
import sys
import os

#Функция проверки отдает весь файл до конца. Если че то не влезло он докинет до конца
def recv_exc(socket, n):
    "читает ровно n байт из сокета. Блокирует пока не получит все"
    buf = b""
    while len(buf) < n:
        chunk = socket.recv(n-len(buf))
        if not chunk:
            raise RuntimeError("Сервер закрыл соединение")
        buf += chunk
        return buf

 # Функция отправки   
def send_rinex(host: str, port: int, filepath: str):
    if not os.path.isfile(filepath):
        print(f"Ошибка, файла нет - {filepath}")
        return

    with open(filepath, "rb") as f:
        file_data = f.read()
    filename = os.path.basename(filepath)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as SERVER:
        SERVER.connect((host, port))

    #Отправка файлов
    SERVER.sendall(struct.pack('>I', len(filename)))
    SERVER.sendall(filename.encode('utf-8'))

    SERVER.sendall(struct.pack('>Q', len(file_data)))
    SERVER.sendall(file_data)

    #Прием ответа
    prefix = recv_exc(SERVER, 4)

    if prefix == b"OK::":
        size_bytes = recv_exc(SERVER, 8)
        result_size = struct.unpack('>Q', size_bytes)[0]

        result = recv_exc(SERVER, result_size)
        print("\n===Результат обработки")
        print(result.decode('utf-8'))

    elif prefix.startswith(b"ERR"):
        rest = SERVER.recv(1024)
        full_error = (prefix + rest).decode('utf-8', errors='repalce')
        print("Сервер вернул ошибку:", full_error)
    else:
        print("Некорректный ответ от сервера:", repr(prefix))

if __name__ == '__main__':
    if len(sys.argv) !=2:
        print("Использовать клиент так: pyhon client.py <путь к файл_измерений.obs>")
        sys.exit(1)
        send_rinex('localhost', 8888, sys.argv[1])