#! /bin/env python3
from base64 import b32encode
import cgi
import cgitb
from contextlib import contextmanager
import hashlib
import logging
import shutil
import sys
import sqlite3
import os
from posix import urandom
from urllib.parse import urljoin

# setup logging
logging.basicConfig(filename='f1l3.log',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)
generic_logger = logging.getLogger('')
db_logger = logging.getLogger("DATABASE")
# some configurations
FILE_CHUNK_SIZE = 204800
UPLOAD_DIR = './files'

request_scheme = os.environ.get('REQUEST_SCHEME', 'http')
server_name = os.environ.get('SERVER_NAME', 'localhost')
HOST = request_scheme + '://' + server_name
FILE_URL = HOST + '/files/'
DATABASE = 'f1l3.sqlite3'

os.makedirs(UPLOAD_DIR, exist_ok=True)

# http response
def make_resp(html=''):
    print("Content-type: text/html\r\n")
    print(html)
def read_html(path):
    with open(path, 'r') as f:
        return f.read()
def index_resp():
    make_resp(read_html('./html/index.html'))

# number/url encoding
decodable = list(range(48, 58)) + \
    list(range(65, 91)) + \
    list(range(97, 123)) + [95, 126]
decodable_count = len(decodable)

def encode_number(num):
    result = []
    while num >= 1:
        remainder = int(num % decodable_count)
        encoded_number = decodable[remainder]
        num /= decodable_count
        result.append(chr(encoded_number))
    return ''.join(result[::-1])

def decode_number(num):
    result = 0
    for i, c in enumerate(reversed(num)):
        base = decodable.index(ord(c))
        result += base * (decodable_count ** i)
    return result

# database
def check_db():
    return os.path.isfile(DATABASE)
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute(
        '''
        CREATE TABLE general_info
        (name text NOT NULL UNIQUE, val text)
        '''
    )
    c.execute(
        '''
        INSERT INTO general_info VALUES ('next_file_id', '1')
        '''
    )
    c.execute(
        '''
        CREATE TABLE file
        (file_name text NOT NULL UNIQUE, sha1 text NOT NULL UNIQUE)
        '''
    )
    conn.commit()
    conn.close()
@contextmanager
def db_cursor():
    if not check_db():
        init_db()
    conn = sqlite3.connect(DATABASE)
    yield conn.cursor()
    conn.commit()
    conn.close()

# upload handling
def is_utf8(path):
    with open(path, 'rb') as f:
        b = f.read(2048)
    try:
        b.decode('utf-8')
    except UnicodeDecodeError:
        return False
    else:
        return True

def rand_str(length=10):
    b = urandom(length)
    k = b32encode(b)
    return str(k, encoding='utf-8')

def handle_upload():
    form = cgi.FieldStorage()
    if not 'upload' in form.keys():
        index_resp()
        return
    uploaded_file = form['upload']
    if not uploaded_file.file:
        index_resp()
        return
    temp_path = "/tmp/" + rand_str()
    sha1_val = hashlib.sha1()
    with open(temp_path, 'wb') as f:
        while True:
            chunk = uploaded_file.file.read(FILE_CHUNK_SIZE)
            if not chunk: break
            f.write(chunk)
            sha1_val.update(chunk)
    sha1_str = sha1_val.hexdigest()
    with db_cursor() as c:
        c.execute(
            '''
            SELECT file_name FROM file WHERE sha1=?
            ''',
            (sha1_str, )
        )
        file_row = c.fetchone()
    if file_row is not None:
        filename = file_row[0]
        os.remove(temp_path)
        make_resp(urljoin(FILE_URL, filename))
        return
    filename = uploaded_file.filename
    ext = os.path.splitext(filename)[1] if filename else ''
    if not ext:
        ext = '.txt' if is_utf8(temp_path) else '.bin'
    with db_cursor() as c:
        c.execute(
            '''
            SELECT val FROM general_info where name='next_file_id'
            '''
        )
        file_id = int(c.fetchone()[0])
        db_logger.info("new file uploaded, id:" + str(file_id))
        encoded_filename = encode_number(file_id) + str(ext)
        c.execute(
            '''
            INSERT INTO file VALUES (?, ?)
            ''',
            (encoded_filename, sha1_str)
        )
        c.execute(
            '''
            UPDATE general_info SET val=? WHERE name='next_file_id'
            ''',
            (str(file_id + 1), )
        )

    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, encoded_filename))
    shutil.move(temp_path, file_path)
    make_resp(urljoin(FILE_URL, encoded_filename))


cgitb.enable()
method = os.environ.get('REQUEST_METHOD', 'GET')

if method == 'GET':
    index_resp()
elif method == 'POST':
    handle_upload()
