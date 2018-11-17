import itertools
import logging
import monero
import monero.backends.jsonrpc
import os
import re
import requests
import shutil
import subprocess
import tempfile
import time

__version__ = '0.1'

_log = logging.getLogger(__name__)


class CommunicationError(Exception):
    pass


class WalletCreationError(CommunicationError):
    pass


class WalletManager(object):
    directory = '.'
    cmd_cli = 'monero-wallet-cli'
    cmd_rpc = 'monero-wallet-rpc'
    daemon_host = '127.0.0.1'
    daemon_port = 18081
    net = 'mainnet'
    rpc_port_range = (18090, 18200)     # like in range()

    def __init__(self, directory=None, net=None, cmd_cli=None, cmd_rpc=None,
            daemon_host=None, daemon_port=None, rpc_port_range=None):
        self.directory = directory or self.directory
        self.cmd_cli = cmd_cli or self.cmd_cli
        self.cmd_rpc = cmd_rpc or self.cmd_rpc
        self.net = net or self.net
        self.daemon_host = daemon_host or self.daemon_host
        self.daemon_port = daemon_port or self.daemon_port
        self.rpc_port_range = rpc_port_range or self.rpc_port_range
        self._rpc_port_gen = itertools.cycle(range(*self.rpc_port_range))
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
        return out, err

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
            out, _ = self._shutdown(wcreate)
            if not os.path.exists(wfile):
                error_re = re.compile(r'(Error:.*)').search(out.decode('utf-8'))
                if error_re:
                    raise WalletCreationError(error_re.groups()[0])
                raise WalletCreationError('Unknown error')
            kfile = '%s.keys' % wfile
            shutil.move(wfile, os.path.join(self.directory, str(address)))
            shutil.move(kfile, os.path.join(self.directory, '%s.keys' % str(address)))
            return address

    def generate_wallet(self):
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
            addr_re = re.compile(r'Generated new wallet:\s([^\s]+)').search(out.decode('utf-8'))
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

    def open_wallet(self, address):
        port = next(self._rpc_port_gen)
        args = [self.cmd_rpc,
                '--wallet-file', os.path.join(self.directory, str(address)),
                '--rpc-bind-port', str(port),
                '--disable-rpc-login']
        args.extend(self._common_args())
        _log.debug(' '.join(args))
        return WalletConnection(address, port, args)


class WalletConnection(object):
    def __init__(self, address, port, args):
        self.port = port
        self._wallet_rpc = subprocess.Popen(args, bufsize=0,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        retries = 0
        while True:
            time.sleep(3)
            try:
                self.wallet = monero.wallet.Wallet(
                    monero.backends.jsonrpc.JSONRPCWallet(port=port))
                break
            except requests.exceptions.ConnectionError:
                if retries >= 10:
                    raise CommunicationError('Could not connect to wallet RPC in 10 retries.')
                retries += 1
        assert self.wallet.address() == address
        self.address = address

    def close(self):
        self._wallet_rpc.terminate()
        tmout = 0
        while not self._wallet_rpc.poll():
            time.sleep(1)
            tmout += 1
            if tmout >= 10:
                self._wallet_rpc.kill()
                break


class WalletPool(object):
    manager = None
    running = None
    max_running = 10
    bc_height = 0
    treat_as_synced_height_diff = 1

    def __init__(self, manager, max_running=None,
            daemon_host='127.0.0.1', daemon_port=18081, daemon_user='', daemon_password=''):
        self.manager = manager or self.manager
        if self.manager is None:
            raise ValueError('Cannot run pool with no WalletManager.')
        self.max_running = max_running or self.max_running
        self.daemon = monero.daemon.Daemon(
            monero.backends.jsonrpc.JSONRPCDaemon(
                host=daemon_host, port=daemon_port, user=daemon_user, password=daemon_password))
        self.running = {}
        self._synced = set()

    def next_addr(self):
        """Method which gets another address to be monitored. Returns address or None if no more
        addresses available at the moment. It must not block."""
        raise NotImplementedError('Subclass {cls} to implement next_addr()'.format(cls=type(self)))

    def before_wallet_start(self, address):
        _log.info('starting {addr}'.format(addr=address))

    def after_wallet_start(self, connection):
        _log.info(' started {addr}'.format(addr=connection.address))

    def after_wallet_synced(self, connection):
        _log.info('  SYNCED {addr}'.format(addr=connection.address))

    def before_wallet_stop(self, connection):
        _log.info('stopping {addr}'.format(addr=connection.address))

    def after_wallet_stop(self, address):
        _log.info(' stopped {addr}'.format(addr=address))

    def run(self):
        while True:
            self.bc_height = self.daemon.height()
            _log.info('Running: {}'.format(len(self.running)))
            while len(self.running) < self.max_running:
                newaddr = str(self.next_addr())
                if newaddr is None or newaddr in self.running:
                    # don't start duplicates
                    continue
                self.before_wallet_start(newaddr)
                cx = self.manager.open_wallet(newaddr)
                self.running[newaddr] = cx
                self.after_wallet_start(cx)
            for addr, cx in list(self.running.items()):
                wh = cx.wallet.height()
                synced = self.bc_height - wh <= self.treat_as_synced_height_diff
                if synced:
                    self._synced.add(addr)
                    self.after_wallet_synced(cx)
                    self.before_wallet_stop(cx)
                    cx.close()
                    del self.running[addr]
                    self.after_wallet_stop(addr)
                time.sleep(1)
            time.sleep(10)
