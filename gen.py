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
                '--daemon-address', '%s:%s' % (self.daemon_host, self.daemon_port)]
        if self.net == 'stagenet':
            args.append('--stagenet')
        elif self.net == 'testnet':
            args.append('--testnet')
        return args

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
            out, err = wcreate.communicate()
            tmout = 0
            while not wcreate.poll():
                time.sleep(1)
                tmout += 1
                if tmout >= 10:
                    wcreate.kill()
                    break
            kfile = '%s.keys' % wfile
            shutil.move(wfile, os.path.join(self.directory, str(address)))
            shutil.move(kfile, os.path.join(self.directory, '%s.keys' % str(address)))
            return address


if __name__ == '__main__':
    import sys
    try:
        directory = sys.argv[1]
    except IndexError:
        directory = None
    wf = WalletManager(directory=directory, daemon_port=38081, net='stagenet')
    while True:
        print(wf.gen_wallet())
