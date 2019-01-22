import collections
import datetime
import itertools
import logging
import monero
import monero.backends.jsonrpc
import os
import re
import requests
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

__version__ = '0.1'

_log = logging.getLogger(__name__)


class CommunicationError(Exception):
    pass


class WalletCreationError(CommunicationError):
    pass


class DaemonClient(object):
    daemon_host = '127.0.0.1'
    daemon_port = 18081

    def __init__(self, **kwargs):
        self.daemon_host = kwargs.pop('daemon_host', self.daemon_host)
        self.daemon_port = kwargs.pop('daemon_port', self.daemon_port)
        super(DaemonClient, self).__init__(**kwargs)

    def daemon_connection_params(self):
        return {'daemon_host': self.daemon_host, 'daemon_port': self.daemon_port}

    def connect_daemon(self):
        self.daemon = monero.daemon.Daemon(monero.backends.jsonrpc.JSONRPCDaemon(
                host=self.daemon_host, port=self.daemon_port))
        return self.daemon


class WalletsManager(DaemonClient):
    """Manages a directory of wallets. Can list, create, open and generate wallets."""
    directory = '.'
    cmd_cli = 'monero-wallet-cli'
    cmd_rpc = 'monero-wallet-rpc'
    net = 'mainnet'

    def __init__(self, directory=None, net=None, cmd_cli=None, cmd_rpc=None, rpc_port_range=None,
            **kwargs):
        self.directory = directory or self.directory
        self.cmd_cli = cmd_cli or self.cmd_cli
        self.cmd_rpc = cmd_rpc or self.cmd_rpc
        self.net = net or self.net
        assert self.net in ('mainnet', 'stagenet', 'testnet')
        assert os.path.exists(self.directory) and os.path.isdir(self.directory)
        super(WalletsManager, self).__init__(**kwargs)

    def _common_args(self):
        args = ['--password', '',
                '--daemon-address', '%s:%s' % (self.daemon_host, self.daemon_port),
                '--trusted-daemon',
                '--log-file', '/dev/null']
        if self.net == 'stagenet':
            args.append('--stagenet')
        elif self.net == 'testnet':
            args.append('--testnet')
        return args

    def _shutdown(self, wpopen):
        out, err = wpopen.communicate()
        _log.debug('stdout: %s' % out.decode())
        _log.debug('stderr: %s' % err.decode())
        tmout = 0
        while not wpopen.poll():
            time.sleep(1)
            tmout += 1
            if tmout >= 10:
                wpopen.kill()
                break
        return out, err

    def list_wallets(self):
        """Returns a sequence of wallet addresses that are available to this manager.
        Uninitialized wallets will be first in the sequence.
        """
        addresses = collections.deque()
        for i in os.listdir(self.directory):
            # scan the directory for *.keys files, assume that * is the address
            if not i.endswith('.keys'):
                continue
            try:
                addr = monero.address.Address(i.replace('.keys', ''))
            except ValueError:
                pass
            if self.net == 'mainnet' and not addr.is_mainnet() \
                or self.net == 'stagenet' and not addr.is_stagenet() \
                or self.net == 'testnet' and not addr.is_testnet():
                continue
            if os.path.exists(os.path.join(self.directory, str(addr))):
                addresses.append(addr)
            else:
                # wallet is not initialized (only .keys file), add it at the beginning
                addresses.appendleft(addr)
        return addresses

    def create_wallet(self, address, viewkey):
        """Creates a view-only wallet."""
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
        """Generates a random wallet and returns the address."""
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

    def open_wallet(self, address, port):
        """Starts RPC server for the wallet and returns its Popen object."""
        args = [self.cmd_rpc,
                '--wallet-file', os.path.join(self.directory, str(address)),
                '--rpc-bind-port', str(port),
                '--disable-rpc-login']
        args.extend(self._common_args())
        _log.debug(' '.join(args))
        return subprocess.Popen(args, bufsize=0,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


WALLET_STARTING = 'starting'
WALLET_SYNCING = 'syncing'
WALLET_SYNCED = 'synced'
WALLET_CLOSING = 'closing'
WALLET_CLOSED = 'closed'
WALLET_FAILED = 'failed'


class WalletController(DaemonClient, threading.Thread):
    """A threat that controls running wallet. Needs a daemon connection to determine whether
    wallet height is up to date (synced). Exposes three fields:
        * `status` - indicates the state of the wallet, where `WALLET_SYNCED` means a running and
          fully synced wallet,
        * `wallet` - the `monero.wallet.Wallet` object that allows talking to wallet API.
        * `shut_down` - a flag which causes the wallet to shut down gracefully once set to `True`.
    """
    status = WALLET_STARTING
    wallet = None
    shut_down = False   # set from external thread to stop this WalletController
    treat_as_synced_height_diff = 1
    # The following specifies retries * sleep for opening a wallet.
    # Default 100 sec may fail on fresh wallets. Don't panic.
    init_sleep = 10
    init_retries = 10
    start_time = None       # datetime.datetime of starting
    running_time = None     # datetime.timedelta of running time

    def __init__(self, address, port, manager, **kwargs):
        self.port = port
        self.address = address
        self.manager = manager
        self.start_time = datetime.datetime.now()
        super(WalletController, self).__init__(name=str(address), **kwargs)
        self.connect_daemon()

    def run(self):
        _log.debug('run(): {}'.format(self.address))
        self.init()
        try:
            while self.daemon.height() > self.wallet.height() + self.treat_as_synced_height_diff:
                time.sleep(10)
            self.status = WALLET_SYNCED
            while not self.shut_down:
                time.sleep(1)
        finally:
            self.close()

    def is_alive(self):
        if self._wallet_rpc.poll() is None:
            _log.debug('Wallet {} is alive.'.format(self.address))
            return True
        return False

    def init(self):
        self._wallet_rpc = self.manager.open_wallet(self.address, self.port)
        try:
            retries = 0
            while True:
                if not self.is_alive():
                    out, err = self._wallet_rpc.communicate()
                    raise RuntimeError('Wallet {} has stopped with exit code {}\n' \
                            'stdout:\n{}\nstderr:\n{}\n'.format(
                            self.address, self._wallet_rpc.returncode, out.decode(), err.decode()))
                try:
                    wallet = monero.wallet.Wallet(
                        monero.backends.jsonrpc.JSONRPCWallet(port=self.port))
                    break
                except requests.exceptions.ConnectionError:
                    if retries >= 10:
                        self.status = WALLET_FAILED
                        raise CommunicationError('Could not connect to wallet RPC in 10 retries.')
                    retries += 1
                time.sleep(10)
            waddr = wallet.address()
            if waddr != self.address:
                self.status = WALLET_FAILED
                raise CommunicationError('Wallet address {} is not the same as address passed in constructor: {}'\
                        .format(waddr, self.address))
            self.wallet = wallet
            self.status = WALLET_SYNCING
        except Exception as e:
            self.close(final_status=WALLET_FAILED)
            raise

    def close(self, final_status=WALLET_CLOSED):
        self.status = WALLET_CLOSING
        if not self.is_alive():
            self._wallet_rpc.terminate()
        tmout = 0
        while not self._wallet_rpc.poll():
            time.sleep(1)
            tmout += 1
            if tmout >= 10:
                self._wallet_rpc.kill()
                break
        self.status = final_status
        self.running_time = datetime.datetime.now() - self.start_time


class WalletPool(DaemonClient):
    """Runs a pool of wallets in given directory. This class should not be run directly
    but subclassed and equipped in some of the event handling methods:
    `main_loop_cycle`, `next_addr`, `wallet_started`, `wallet_synced`, `wallet_closed`
    """
    manager = None
    running = None
    rpc_port_range = (18090, 18200)     # like in range()
    max_running = 2
    main_loop_sleep_time = 5
    bc_height = 0

    def __init__(self, manager, max_running=None, **kwargs):
        self.manager = manager or self.manager
        if self.manager is None:
            raise ValueError('Cannot run pool with no WalletManager.')
        self._rpc_port_gen = itertools.cycle(range(*self.rpc_port_range))
        self.max_running = min(
            max_running or self.max_running,
            self.rpc_port_range[1] - self.rpc_port_range[0])
        self.running = {}
        super(WalletPool, self).__init__(**kwargs)

    def main_loop_cycle(self):
        """Launched on every iteration of the main loop."""
        _log.debug('Running {}/{} wallet(s).'.format(len(self.running), self.max_running))

    def next_addr(self):
        """Method which gets another address to be monitored. Returns address or None if no more
        addresses available at the moment. It must not block."""
        raise NotImplementedError('Subclass {cls} to implement next_addr()'.format(cls=type(self)))

    def wallet_started(self, ctrl):
        _log.debug('Wallet {} started.'.format(ctrl.address))

    def wallet_synced(self, ctrl):
        _log.warning('Wallet {} synced but the handler does nothing.'.format(ctrl.address))

    def wallet_closed(self, ctrl):
        _log.debug('Wallet {} closed.'.format(ctrl.address))

    def wallet_failed(self, ctrl):
        _log.debug('Wallet {} failed.'.format(ctrl.address))

    def main_loop(self):
        signal.signal(signal.SIGINT, self.stop)
        while True:
            self.main_loop_cycle()
            while len(self.running) < self.max_running:
                newaddr = str(self.next_addr())
                if newaddr is None or newaddr in self.running:
                    # don't start duplicates
                    continue
                ctrl = WalletController(newaddr, next(self._rpc_port_gen), self.manager,
                        **self.daemon_connection_params())
                self.running[newaddr] = ctrl
                ctrl.start()
                self.wallet_started(ctrl)
            for addr, ctrl in list(self.running.items()):
                _log.debug('{}: {}'.format(addr[:6], ctrl.status))
                if ctrl.status == WALLET_SYNCED:
                    self.wallet_synced(ctrl)
                elif ctrl.status == WALLET_CLOSED:
                    self.wallet_closed(ctrl)
                    ctrl.join()
                    del self.running[addr]
                elif ctrl.status == WALLET_FAILED:
                    self.wallet_failed(ctrl)
                    ctrl.join()
                    del self.running[addr]
            time.sleep(self.main_loop_sleep_time)

    def stop(self, *args):
        _log.info('SIGINT received, cleaning up.')
        for addr, ctrl in self.running.items():
            _log.info('{}: {}'.format(addr[:6], ctrl.status))
            ctrl.shut_down = True
        for _, ctrl in self.running.items():
            _log.info('Waiting for {} to stop'.format(ctrl.address))
            ctrl.join()
        sys.exit(0)
