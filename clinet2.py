import socket
import struct
import sys
import os


def recv_exactly(sock, n):
    """Читает ровно n байт из сокета. Блокирует, пока не получит все."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("Сервер закрыл соединение")
        buf += chunk
    return buf


def send_rinex(host: str, port: int, rover_file: str, base_file: str):
    files_to_send = [rover_file, base_file]

    for filepath in files_to_send:
        if not os.path.isfile(filepath):
            print(f"Ошибка: файл не найден — {filepath}")
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))

         # --- Отправка количества файлов (2) ---
        s.sendall(struct.pack('>I', 2))

        # --- Отправка двух файлов ---
        for filepath in files_to_send:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            filename = os.path.basename(filepath)

        # --- Отправка файла ---
            s.sendall(struct.pack('>I', len(filename)))      # длина имени (4 байта)
            s.sendall(filename.encode('utf-8'))              # имя файла
            s.sendall(struct.pack('>Q', len(file_data)))     # размер файла (8 байт)
            s.sendall(file_data)                             # содержимое

        # --- Приём ответа ---
        # Читаем первые 4 байта для определения типа ответа
        prefix = recv_exactly(s, 4)

        if prefix == b"OK::":
            # Успех: читаем 8 байт — длину результата
            size_bytes = recv_exactly(s, 8)
            result_size = struct.unpack('>Q', size_bytes)[0]

            # Читаем сам результат (ровно result_size байт)
            result = recv_exactly(s, result_size)

            print("\n=== Результат обработки ===")
            print(result.decode('utf-8'))

        elif prefix.startswith(b"ERR"):  # например, b"ERRO" от "ERROR:..."
            # Дочитываем остаток сообщения об ошибке
            rest = s.recv(1024)
            full_error = (prefix + rest).decode('utf-8', errors='replace')
            print("Сервер вернул ошибку:", full_error)

        else:
            print("Некорректный ответ от сервера:", repr(prefix))



if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Использование: python client.py <rover_file.obs> <base_file.obs>")
        print("  rover_file.obs - файл наблюдений подвижного приемника")
        print("  base_file.obs  - файл наблюдений базовой станции")
        sys.exit(1)
    rover_file = sys.argv[1]
    base_file = sys.argv[2]
send_rinex('192.168.1.100', 9999, rover_file, base_file)
