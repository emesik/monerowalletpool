import collections
import itertools
import logging
import monero
import os
import sys
from monerowalletpool import WalletsManager, WalletPool

_log = logging.getLogger(__name__)

class DirPool(WalletPool):
    """A pool instance watching over a directory of wallets.
    Each wallet file is supposed to be named by its master address.
    """
    def __init__(self, manager, **kwargs):
        addresses = manager.list_wallets()
        self._addresses = itertools.cycle(addresses)
        _log.info('Pool has {} addresses.'.format(len(addresses)))
        super(DirPool, self).__init__(manager, **kwargs)

    def next_addr(self):
        return next(self._addresses)

    def wallet_started(self, ctrl):
        _log.info('Started: {}'.format(ctrl.address[:6]))

    def wallet_synced(self, ctrl):
        _log.info('{} Incoming: [{}]'.format(
                ctrl.address[:6],
                ','.join(map(lambda p: '{:4.12f}'.format(p.amount), ctrl.wallet.incoming()))))
        _log.info('{} Outgoing: [{}]'.format(
                ctrl.address[:6],
                ','.join(map(lambda p: '{:4.12f}'.format(p.amount), ctrl.wallet.outgoing()))))
        ctrl.shut_down = True

if __name__ == '__main__':
    def usage():
        print('Usage: {} <directory> [daemonhost:port]'.format(*sys.argv), file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        usage()
    host = '127.0.0.1'
    port = 18081
    if len(sys.argv) == 3:
        try:
            host, port = sys.argv[2].split(':')
            port = int(port)
        except:
            usage()
    pool = DirPool(
            WalletsManager(
                directory=sys.argv[1],
                net='stagenet',
                daemon_host=host,
                daemon_port=port),
            daemon_host=host,
            daemon_port=port)
    pool.main_loop()
