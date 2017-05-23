import unittest
import nasg.jinjaenv as jinjaenv
import arrow

class CommandLineTest(unittest.TestCase):

    def test_jinja_filter_date(self):
        t = arrow.utcnow()
        self.assertEqual(
            jinjaenv.jinja_filter_date(t.datetime, 'c'),
            t.format('YYYY-MM-DDTHH:mm:ssZ')
        )

    def test_jinja_filter_slugify(self):
        self.assertEqual(
            jinjaenv.jinja_filter_slugify('Árvíztűrő Tükörfúrógép'),
            'arvizturo-tukorfurogep'
        )

    def test_jinja_filter_search1(self):
        self.assertTrue(
            jinjaenv.jinja_filter_search('almafa', 'alma')
        )

    def test_jinja_filter_search3(self):
        self.assertTrue(
            jinjaenv.jinja_filter_search( ['almafa' ], 'almafa')
        )

    def test_jinja_filter_search2(self):
        self.assertFalse(
            jinjaenv.jinja_filter_search('almafa', 'eszeveszett')
        )

if __name__ == '__main__':
    unittest.main()