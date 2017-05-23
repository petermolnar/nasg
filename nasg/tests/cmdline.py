import unittest
import nasg.cmdline as cmdline

class Test(unittest.TestCase):

    def testException(self):
        self.assertRaises(
            ValueError,
            cmdline.CommandLine,
            '12345678'
        )

    def testOK(self):
        self.assertEqual(
            cmdline.CommandLine('ls ./test_cmdline.py').run().stdout,
            './test_cmdline.py'
        )

    def testExiftool(self):
        self.assertEqual(
            cmdline.Exiftool().get(),
            {}
        )

if __name__ == '__main__':
    unittest.main()