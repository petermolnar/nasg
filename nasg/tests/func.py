import unittest
import nasg.func as func


class Test(unittest.TestCase):

    def test_baseN_zero(self):
        self.assertEqual(
            func.baseN(0),
            '0'
        )

    def test_baseN(self):
        self.assertEqual(
            func.baseN(1489437846),
            'omrtli'
        )

    def test_gps2dec_W(self):
        self.assertEqual(
            func.gps2dec(
                '103 deg 52\' 32.79" W'
            ),
            -103.875775
        )

    def test_gps2dec_E(self):
        self.assertEqual(
            func.gps2dec(
                '103 deg 52\' 32.79" E'
            ),
            103.875775
        )

    def test_gps2dec_N(self):
        self.assertEqual(
            func.gps2dec(
                '33 deg 9\' 34.93" N'
            ),
            33.159703
        )

    def test_gps2dec_S(self):
        self.assertEqual(
            func.gps2dec(
                '33 deg 9\' 34.93" S'
            ),
            -33.159703
        )

    def test_gps2dec(self):
        self.assertEqual(
            func.gps2dec(
                '33 deg 9\' 34.93"'
            ),
            33.159703
        )

if __name__ == '__main__':
    unittest.main()