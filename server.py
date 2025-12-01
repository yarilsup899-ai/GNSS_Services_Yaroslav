import socket
import struct
import tempfile
import os
import subprocess
import traceback
from datetime import date

import urllib.request
import gzip


def download_brdc_from_bkg(obs_date: date, out_dir: str) -> str:
    """
    Скачивает суточный BRDC-файл эфемерид с BKG (https://igs.bkg.bund.de).
    Возвращает путь к распакованному RINEX-файлу (.YYn).
    """
    year = obs_date.year
    doy = obs_date.strftime('%j')  # день года, например: '291'
    yy = obs_date.strftime('%y')   # '25'

    # Имя файла: brdc2910.25n.gz
    filename_gz = f"brdc{doy}0.{yy}n.gz"
    url = f"https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy}/BRDC00IGS_R_{year}{doy}0000_01D_MN.rnx.gz"

    out_gz = os.path.join(out_dir, filename_gz)
    out_rnx = os.path.join(out_dir, filename_gz[:-3])  # убираем .gz → .25n

    print(f"Скачивание эфемерид с BKG: {url}")

    try:
        # Скачиваем .gz
        urllib.request.urlretrieve(url, out_gz)

        # Распаковываем
        with gzip.open(out_gz, 'rb') as gz_in:
            with open(out_rnx, 'wb') as rnx_out:
                rnx_out.write(gz_in.read())

        # Удаляем архив
        os.remove(out_gz)

        return out_rnx

    except Exception as e:
        if os.path.exists(out_gz):
            os.remove(out_gz)
        if os.path.exists(out_rnx):
            os.remove(out_rnx)
        raise RuntimeError(f"Не удалось скачать или распаковать эфемериды с BKG: {e}")


def extract_date_from_rinex(rnx_path: str) -> date:
    """Извлекает дату из RINEX-файла (поддержка v2 и v3)."""
    with open(rnx_path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
        if not first_line or 'RINEX VERSION / TYPE' not in first_line:
            raise ValueError("Файл не является RINEX")
        
        try:
            version = float(first_line.split()[0])
        except:
            raise ValueError("Не удалось определить версию RINEX")

        for line in f:
            if 'TIME OF FIRST OBS' in line:
                parts = line.split()
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return date(year, month, day)
    raise ValueError("Не найдена дата в RINEX-файле")


def run_rtklib_rel(base_obs_file: str, rover_obs_file: str, nav_file: str, out_file: str):
    """Запускает rnx2rtkp в режиме rel (Relative)."""
    cmd = ["/Users/sergeidolin/RTKLIB/app/consapp/rnx2rtkp/gcc/rnx2rtkp", "-p", "3", "-o", out_file, rover_obs_file, base_obs_file, nav_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"RTKLIB ошибка:\n{result.stderr}")

def recv_exactly(sock, n):
    """Читает ровно n байт из сокета."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("Клиент разорвал соединение")
        buf += chunk
    return buf


def handle_client(conn):
    print(f"[Сервер] Начало обработки клиента")
    rover_path = base_path = obs_path = eph_path = result_path = None
    try:
        # Получаем имя файла rover
        name_len = struct.unpack('>I', recv_exactly(conn, 4))[0]
        rover_filename = recv_exactly(conn, name_len).decode('utf-8')
        file_size = struct.unpack('>Q', recv_exactly(conn, 8))[0]

        # Сохраняем RINEX во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.25o') as f:
            rover_path = f.name
            total = 0
            while total < file_size:
                chunk = conn.recv(min(65536, file_size - total))
                if not chunk:
                    raise RuntimeError("Клиент разорвал соединение")
                f.write(chunk)
                total += len(chunk)

        # Получаем имя файла base
        name_len = struct.unpack('>I', recv_exactly(conn, 4))[0]
        base_filename = recv_exactly(conn, name_len).decode('utf-8')
        file_size = struct.unpack('>Q', recv_exactly(conn, 8))[0]

        # Сохраняем RINEX во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.25o') as f:
            base_path = f.name
            total = 0
            while total < file_size:
                chunk = conn.recv(min(65536, file_size - total))
                if not chunk:
                    raise RuntimeError("Клиент разорвал соединение")
                f.write(chunk)
                total += len(chunk)

        # Извлекаем дату
        obs_date = extract_date_from_rinex(obs_path)

        # Скачиваем эфемериды ЧЕРЕЗ MONCENTERLIB
        eph_path = download_brdc_from_bkg(obs_date, out_dir=os.path.dirname(obs_path))

        # Запускаем RTKLIB напрямую
        result_path = obs_path.replace('.25o', '.pos')
        run_rtklib_rel(obs_path, eph_path, result_path)

        # Отправляем результат клиенту
        # Читаем .pos и извлекаем последнюю строку с решением
        last_solution_line = ""
        with open(result_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('%'):
                    last_solution_line = line

        if not last_solution_line:
            raise RuntimeError("В .pos-файле не найдено решений")

        result_text = last_solution_line + "\n"
        result_data = result_text.encode('utf-8')

        # Отправляем успешный результат
        conn.sendall(b"OK::")
        conn.sendall(struct.pack('>Q', len(result_data)))
        conn.sendall(result_data)

    except Exception as e:
        error_msg = str(e).strip()
        if not error_msg:
            error_msg = "Неизвестная ошибка"
        full_msg = f"ERR:{error_msg}"
        try:
            conn.sendall(full_msg.encode('utf-8'))
        except Exception as send_err:
            print(f"[Сервер] Не удалось отправить ошибку клиенту: {send_err}")
            print(f"[Сервер] Оригинальная ошибка: {e}")
            traceback.print_exc()
    finally:
        conn.close()
        # Удаляем временные файлы
        for p in [obs_path, eph_path, result_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    print(f"Не удалось удалить {p}: {e}")


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 9999))
    server.listen(5)
    print("Сервер запущен на порту 9999")
    try:
        while True:
            conn, addr = server.accept()
            print(f"Подключение от {addr}")
            handle_client(conn)
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.close()


if __name__ == '__main__':
    main()
