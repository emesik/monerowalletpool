import itertools
import logging
import monero
import os
import random
import sys
from monerowalletpool import WalletManager, WalletPool

_log = logging.getLogger(__name__)

class DirPool(WalletPool):
    def __init__(self, manager, **kwargs):
        addresses = set()
        for i in os.listdir(manager.directory):
            try:
                addresses.add(str(monero.address.Address(i.replace('.keys', ''))))
            except ValueError:
                pass
        addresses = list(addresses)
        random.shuffle(addresses)
        self._addresses = itertools.cycle(addresses)
        _log.info('Pool has {} addresses.'.format(len(addresses)))
        super(DirPool, self).__init__(manager, **kwargs)

    def after_wallet_synced(self, connection):
        print(connection.wallet.incoming())

    def next_addr(self):
        return next(self._addresses)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    pool = DirPool(
            WalletManager(directory=sys.argv[1], net='stagenet', daemon_port=38081),
            daemon_port=38081)
    pool.run()
