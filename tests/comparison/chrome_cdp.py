"""Small stdlib CDP transport for existing local Chrome, no downloaded drivers."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from urllib.request import urlopen
from urllib.parse import urlparse


class ChromeCDP:
    def __init__(self, chrome, root):
        self.root=Path(root);self.profile=self.root/'chrome';self.counter=0
        self.proc=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-first-run',
            '--no-default-browser-check','--disable-background-networking','--disable-component-update',
            '--disable-sync','--host-resolver-rules=MAP * ~NOTFOUND',
            '--remote-debugging-port=0','--user-data-dir='+str(self.profile),'about:blank'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            portfile=self.profile/'DevToolsActivePort'
            self.wait(lambda:portfile.exists())
            port=int(portfile.read_text().splitlines()[0])
            with urlopen('http://127.0.0.1:'+str(port)+'/json/list',timeout=10) as response:
                pages=json.load(response)
            url=urlparse(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
            self.sock=socket.create_connection((url.hostname,url.port),timeout=20)
            key=base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f'GET {url.path} HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            header=b''
            while not header.endswith(b'\r\n\r\n'):header+=self.sock.recv(1)
            assert header.split(b'\r\n',1)[0].split()[1]==b'101',header
            expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
            assert expected in header,header
            self.call('Page.enable');self.call('Runtime.enable')
            self.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(self.root.resolve())})
        except BaseException:
            self.close();raise

    def read(self,n):
        result=b''
        while len(result)<n:
            part=self.sock.recv(n-len(result))
            if not part:raise EOFError('Chrome disconnected')
            result+=part
        return result

    def call(self,method,params=None):
        self.counter+=1;ident=self.counter
        raw=json.dumps({'id':ident,'method':method,'params':params or {}}).encode()
        mask=os.urandom(4);size=len(raw)
        header=bytes([0x81,0x80|size]) if size<126 else bytes([0x81,0x80|126])+struct.pack('!H',size) if size<65536 else bytes([0x81,0x80|127])+struct.pack('!Q',size)
        self.sock.sendall(header+mask+bytes(v^mask[i%4] for i,v in enumerate(raw)))
        while True:
            first,second=self.read(2);size=second&127
            if size==126:size=struct.unpack('!H',self.read(2))[0]
            if size==127:size=struct.unpack('!Q',self.read(8))[0]
            if first&15==8:raise EOFError('Websocket closed')
            data=json.loads(self.read(size))
            if data.get('id')==ident:
                if 'error' in data:raise AssertionError(data['error'])
                return data.get('result',{})

    def evaluate(self,script):
        result=self.call('Runtime.evaluate',{'expression':script,'returnByValue':True,'awaitPromise':True})
        if 'exceptionDetails' in result:raise AssertionError(result['exceptionDetails'])
        return result['result'].get('value')

    def open(self,path):
        # Invalidate the old page before navigating, including same-URL reloads.
        self.evaluate("if(document.documentElement) delete document.documentElement.dataset.reportReady")
        self.call('Page.navigate',{'url':Path(path).resolve().as_uri()})
        def ready():
            try:
                return self.evaluate("!!document.documentElement && document.documentElement.dataset.reportReady==='true'")
            except AssertionError as exc:
                if 'Execution context was destroyed' in str(exc) or 'Cannot find context' in str(exc):
                    return False
                raise
        self.wait(ready)

    def upload(self,selector,path):
        document=self.call('DOM.getDocument')
        node=self.call('DOM.querySelector',{'nodeId':document['root']['nodeId'],'selector':selector})
        self.call('DOM.setFileInputFiles',{'nodeId':node['nodeId'],'files':[str(Path(path).resolve())]})

    @staticmethod
    def wait(predicate,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.05)
        raise AssertionError('Chrome condition timed out')

    def close(self):
        if hasattr(self,'sock'):self.sock.close()
        self.proc.terminate()
        try:self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
