import collections
import itertools
import logging
import monero
import os
import sys
from monerowalletpool import WalletsManager, WalletPool

_log = logging.getLogger(__name__)

class DirPool(WalletPool):
    def __init__(self, manager, **kwargs):
        addresses = collections.deque()
        for i in os.listdir(manager.directory):
            if not i.endswith('.keys'):
                continue
            try:
                addr = monero.address.Address(i.replace('.keys', ''))
            except ValueError:
                pass
            if os.path.exists(os.path.join(manager.directory, str(addr))):
                addresses.append(addr)
            else:
                addresses.appendleft(addr)
        self._addresses = itertools.cycle(addresses)
        _log.info('Pool has {} addresses.'.format(len(addresses)))
        super(DirPool, self).__init__(manager, **kwargs)

    def next_addr(self):
        return next(self._addresses)

    def wallet_synced(self, ctrl):
        print(ctrl.incoming)
        print(ctrl.outgoing)
        ctrl.shut_down = True

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    pool = DirPool(
            WalletsManager(directory=sys.argv[1], net='stagenet', daemon_port=38081),
            daemon_port=38081)
    pool.run()
