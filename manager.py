import logging
import monero
import os
import re
import shutil
import subprocess
import tempfile
import time

_log = logging.getLogger(__name__)


class CommunicationError(Exception):
    pass


class WalletManager(object):
    directory = '.'
    cmd_cli = 'monero-wallet-cli'
    cmd_rpc = 'monero-wallet-rpc'
    daemon_host = '127.0.0.1'
    daemon_port = 18081
    net = 'mainnet'

    def __init__(self, directory=None, cmd_cli=None, cmd_rpc=None, daemon_host=None, daemon_port=None, net=None):
        self.directory = directory or self.directory
        self.cmd_cli = cmd_cli or self.cmd_cli
        self.cmd_rpc = cmd_rpc or self.cmd_rpc
        self.daemon_host = daemon_host or self.daemon_host
        self.daemon_port = daemon_port or self.daemon_port
        self.net = net or self.net
        assert self.net in ('mainnet', 'stagenet', 'testnet')
        assert os.path.exists(self.directory) and os.path.isdir(self.directory)

    def _common_args(self):
        args = ['--password', '',
                '--daemon-address', '%s:%s' % (self.daemon_host, self.daemon_port),
                '--log-file', '/dev/null']
        if self.net == 'stagenet':
            args.append('--stagenet')
        elif self.net == 'testnet':
            args.append('--testnet')
        return args

    def _shutdown(self, wpopen):
        out, err = wpopen.communicate()
        _log.debug('stdout: %s' % out)
        _log.debug('stderr: %s' % err)
        tmout = 0
        while not wpopen.poll():
            time.sleep(1)
            tmout += 1
            if tmout >= 10:
                wpopen.kill()
                break

    def create_wallet(self, address, viewkey):
        with tempfile.TemporaryDirectory() as wdir:
            wfile = os.path.join(wdir, 'wallet')
            _log.debug('Wallet file: %s' % wfile)
            args = [self.cmd_cli,
                    '--generate-from-view-key', wfile]
            args.extend(self._common_args())
            _log.debug(' '.join(args))
            wcreate = subprocess.Popen(args, bufsize=0,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = b''
            while b'Logging' not in out:
                out = wcreate.stdout.readline()
                _log.debug('stdout: %s' % out)
            wcreate.stdin.write(b'%s\n' % str(address).encode('ascii'))
            _log.debug(b'%s\n' % str(address).encode('ascii'))
            wcreate.stdin.write(b'%s\n' % str(viewkey).encode('ascii'))
            wcreate.stdin.write(b'\n\n')
            wcreate.stdin.write(b'0\n')
            # TODO: any sort of error handling
            self._shutdown(wcreate)
            kfile = '%s.keys' % wfile
            shutil.move(wfile, os.path.join(self.directory, str(address)))
            shutil.move(kfile, os.path.join(self.directory, '%s.keys' % str(address)))
            return address

    def gen_wallet(self):
        with tempfile.TemporaryDirectory() as wdir:
            wfile = os.path.join(wdir, 'wallet')
            _log.debug('Wallet file: %s' % wfile)
            args = [self.cmd_cli,
                    '--use-english-language-names']
            args.extend(['--generate-new-wallet', wfile])
            args.extend(self._common_args())
            _log.debug(' '.join(args))
            wcreate = subprocess.Popen(args, bufsize=0,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = b''
            while b'English' not in out:
                out = wcreate.stdout.readline()
                _log.debug('stdout: %s' % out)
            wcreate.stdin.write(b'1\n')
            while b'Generated' not in out:
                out = wcreate.stdout.readline()
                _log.debug('stdout: %s' % out)
            addr_re = re.compile('Generated new wallet:\s([^\s]+)').search(out.decode('utf-8'))
            if not addr_re:
                wcreate.kill()
                raise CommunicationError('Cannot find address')
            address = monero.address.Address(addr_re.groups()[0])
            _log.debug('Address: %s' % address)
            self._shutdown(wcreate)
            kfile = '%s.keys' % wfile
            shutil.move(wfile, os.path.join(self.directory, str(address)))
            shutil.move(kfile, os.path.join(self.directory, '%s.keys' % str(address)))
            return address
