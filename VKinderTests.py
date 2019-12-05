from pymongo import MongoClient
import unittest
import vkinder2

client = MongoClient('localhost', 27017)
bitches_db = client['ticket_db']
b_coll = bitches_db.collection


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
