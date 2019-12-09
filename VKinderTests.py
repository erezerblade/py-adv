from pymongo import MongoClient
import unittest
import vkinder2
from unittest.mock import patch

client = MongoClient('localhost', 27017)
bitches_db = client['ticket_db']
b_coll = bitches_db.collection

USER_DATA = {'id': 4233870,
                     'first_name': 'Леонид',
                     'last_name': 'Кузьмин',
                     'is_closed': False,
                     'can_access_closed': True,
                     'sex': 2,
                     'bdate': '24.5.1991',
                     'city': {'id': 1, 'title': 'Москва'},
                     'interests': 'спорт, саморазвитие, магия, страдания, психоделия, йога, SEO, python',
                     'music': 'Михаил Елизаров, Black Sabbath, Ольга Арефьева, Queen, The Beatles, Judas Priest, '
                              'Metallica',
                     'groups': [44760286,
                                34215577,
                                181088115,
                                116098227,
                                68832026,
                                165205783,
                                72988498,
                                68995594,
                                129762621,
                                38691559,
                                160426659,
                                51048597,
                                35862441,
                                40886007,
                                29534144,
                                72495085,
                                35595350,
                                20629724,
                                38793584,
                                52537634,
                                100419172,
                                129440544,
                                28261334]}


class TestVKinder2(unittest.TestCase):

    def test_get_user_data(self):
        result = vkinder2.get_user_data("erezerblade")
        self.assertCountEqual(result.keys(), (['bdate', 'can_access_closed', 'city', 'first_name', 'groups', 'id',
                                               'interests', 'is_closed', 'last_name', 'music', 'sex']))

    def test_search_for_matches(self):
        result = vkinder2.search_for_matches("erezerblade")
        self.assertIsInstance(result, list)

    def test_add_groups(self):
        result = vkinder2.add_groups("erezerblade")
        self.assertIn('groups', result[0].keys())

    def test_score_matches(self):
        self.assertRaises(KeyError, vkinder2.score_matches, "erezerblade", 6, 6, 6, 6, 6, 6)

    def test_get_top10(self):
        result = vkinder2.get_top10("erezerblade")
        self.assertCountEqual(['photo1', 'photo2', 'photo3', 'profile_url', 'score', 'id', 'first_name', 'last_name',
                               'bdate', 'status', 'relation', 'interests', 'music', 'activities', 'about'],
                              result[0].keys())

    def test_store_to_db(self):
        vkinder2.store_to_db('erezerblade')
        self.assertTrue(list(b_coll.find()))
        self.assertEqual(len(list(b_coll.find())), 10)
