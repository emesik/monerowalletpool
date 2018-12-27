import os
import tempfile
import unittest

from monerowalletpool import WalletsManager, WalletCreationError

class CreateManagers(object):
    def setUp(self):
        self.walletdir = tempfile.TemporaryDirectory()

        self.mainnet_mgr = WalletsManager(directory=self.walletdir.name)
        self.stagenet_mgr = WalletsManager(directory=self.walletdir.name, net='stagenet')
        self.testnet_mgr = WalletsManager(directory=self.walletdir.name, net='testnet')

    def tearDown(self):
        self.walletdir.cleanup()


class GenerateTestCase(CreateManagers, unittest.TestCase):
    def test_generate(self):
        mainnet_addr = self.mainnet_mgr.generate_wallet()
        self.assertTrue(mainnet_addr.is_mainnet())
        self.assertFalse(mainnet_addr.is_stagenet())
        self.assertFalse(mainnet_addr.is_testnet())
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(mainnet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(mainnet_addr)) + '.keys'))

        stagenet_addr = self.stagenet_mgr.generate_wallet()
        self.assertFalse(stagenet_addr.is_mainnet())
        self.assertTrue(stagenet_addr.is_stagenet())
        self.assertFalse(stagenet_addr.is_testnet())
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(stagenet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(stagenet_addr)) + '.keys'))

        testnet_addr = self.testnet_mgr.generate_wallet()
        self.assertFalse(testnet_addr.is_mainnet())
        self.assertFalse(testnet_addr.is_stagenet())
        self.assertTrue(testnet_addr.is_testnet())
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(testnet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(testnet_addr)) + '.keys'))


class CreateValidTestCase(CreateManagers, unittest.TestCase):
    def test_create_valid(self):
        mainnet_addr = self.mainnet_mgr.create_wallet(
            '4ABJ7nTkWCuUnLSvcMasWS4XFLQefSrbqDMC5kuV9JSVeye8fbe6C6NQNMx3VLPvBqLQV9GzsJEkLBu9PxC9o95W8RSSnUQ',
            '346dc4126e113e748457dbceeed3a9c31e4654c75aafa052ea0c26752fa8c905')
        self.assertEqual(
            mainnet_addr,
            '4ABJ7nTkWCuUnLSvcMasWS4XFLQefSrbqDMC5kuV9JSVeye8fbe6C6NQNMx3VLPvBqLQV9GzsJEkLBu9PxC9o95W8RSSnUQ')
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(mainnet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(mainnet_addr)) + '.keys'))

        stagenet_addr = self.stagenet_mgr.create_wallet(
            '548wjYLqNPdNcSPFk3xLSZNGLLHWkwZdvikDftDqeXHJdNZRkh6hNtd9NwVsKeNvAZNwooxGbPa7yZr4tpteBwpHLwnZ6gV',
            '36307366e846ee42110e2fa75a04f9e38f6bf49839da79f96568deae7cfaec0b')
        self.assertEqual(
            stagenet_addr,
            '548wjYLqNPdNcSPFk3xLSZNGLLHWkwZdvikDftDqeXHJdNZRkh6hNtd9NwVsKeNvAZNwooxGbPa7yZr4tpteBwpHLwnZ6gV')
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(stagenet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(stagenet_addr)) + '.keys'))

        testnet_addr = self.testnet_mgr.create_wallet(
            'A1fXttm6hSXKjpPwTQjQac7kJSiSDPKWeCaHCtDtaeenSN3cZiVxsFuMz6cLAQvL3QiQetyEfDGoKRAK5rNm1dLLEWBgqeH',
            '628452958e3c44c95cc790c3ba507fae38640156498e6b1becc4ef8938a09e0f')
        self.assertEqual(
            testnet_addr,
            'A1fXttm6hSXKjpPwTQjQac7kJSiSDPKWeCaHCtDtaeenSN3cZiVxsFuMz6cLAQvL3QiQetyEfDGoKRAK5rNm1dLLEWBgqeH')
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(testnet_addr))))
        self.assertTrue(os.path.exists(os.path.join(self.walletdir.name, str(testnet_addr)) + '.keys'))


class CreateInvalidTestCase(CreateManagers, unittest.TestCase):
    def test_create_invalid(self):
        self.assertRaises(
            WalletCreationError,
            self.mainnet_mgr.create_wallet,
            '4ABJ7nTkWCuUnLSvcMasWS4XFLQefSrbqDMC5kuV9JSVeye8fbe6C6NQNMx3VLPvBqLQV9GzsJEkLBu9PxC9o95W8RSSnUQ',
            '1111111111111111111111111111111111111111111111111111111111111111')
        self.assertRaises(
            WalletCreationError,
            self.stagenet_mgr.create_wallet,
            '548wjYLqNPdNcSPFk3xLSZNGLLHWkwZdvikDftDqeXHJdNZRkh6hNtd9NwVsKeNvAZNwooxGbPa7yZr4tpteBwpHLwnZ6gV',
            '1111111111111111111111111111111111111111111111111111111111111111')
        self.assertRaises(
            WalletCreationError,
            self.testnet_mgr.create_wallet,
            'A1fXttm6hSXKjpPwTQjQac7kJSiSDPKWeCaHCtDtaeenSN3cZiVxsFuMz6cLAQvL3QiQetyEfDGoKRAK5rNm1dLLEWBgqeH',
            '1111111111111111111111111111111111111111111111111111111111111111')
