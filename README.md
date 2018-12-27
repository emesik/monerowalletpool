Monero wallet pool
==================

The standard Monero wallet implementation allows monitoring of a single wallet. This is often not
enough in environments where per-user wallet is required to be constantly watched over.

`monerowalletpool` is an attempt to work around that deficiency by running several instances
of the wallet software, cycling over a larger pool of wallet files.

The pool assumes a simple structure:

 1. All wallets are located in a single directory.
 2. Each wallet is named by its address, e.g.
    `51zfcr92LbRe8Ej9137FYx7h44MvX3PozYM1T9A5G44QR7yAZ9QnQLoCuBcj9UCd2RVmt6zWfSPZaR8iiXkmYnnzBo3pf1L.keys`
    and
    `51zfcr92LbRe8Ej9137FYx7h44MvX3PozYM1T9A5G44QR7yAZ9QnQLoCuBcj9UCd2RVmt6zWfSPZaR8iiXkmYnnzBo3pf1L`

**The code is experimental and not intended for production use.** Currently it is focused on
running view-only wallets.

Example
-------

See `examples/runpool.py` for a pool runner that does nothing more than logging the transactions
from each watched wallet.
