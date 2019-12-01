import requests
import datetime
from pprint import pprint
from pymongo import MongoClient
import time
import re
import vk_api
import json

client = MongoClient('localhost', 27017)
bitches_db = client['ticket_db']
b_coll = bitches_db.collection

ACCESS_TOKEN = '8e57ea278d436f7d4cc85cd868f5c91d47f558a521fa1a8d879c72290d1fd0b6be3d815adfc5adcee4689'


def get_params(expand_params):
    default_params = {
        'v': 5.103,
        'access_token': ACCESS_TOKEN
    }
    default_params.update(expand_params)
    return default_params


# добываем критерии из профиля человека
def get_user_data(user_id):
    data = requests.get('https://api.vk.com/method/users.get', params=get_params({
        'user_ids': str(user_id),
        'extended': 1,
        'fields': "bdate, music, city, interests, sex"})).json()['response'][0]
    # пользователь добавляет свою дату рождения
    if not data.get('bdate') or len(data.get('bdate')) < 8:
        bdate = str(input('Введите свою дату рождения в формате ДД.ММ.ГГГГ: '))
        if re.match(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4}", bdate):
            data.update({'bdate': bdate})
        else:
            raise KeyError('Вы ввели неправильную дату рождения, попробуйте ещё раз')
    # пользователь добавляет свой город
    if not data.get('city'):
        city = requests.get('https://api.vk.com/method/database.getCities', params=get_params({
            'country_id': 1,
            'q': str(input('Введите название своего города: ')),
            'count': 1})).json()
        if 'error' not in city.keys():
            data.update(city['response']['items'][0])
        else:
            raise KeyError('Ваш город не найден, попробуйте ещё раз')
    # пользователь добавляет свой пол
    if not data.get('sex'):
        sex = str(input('Введите ваш пол в формате М или Ж: '))
        if sex == 'M':
            data.update({'sex': 2})
        elif sex == 'Ж':
            data.update({'sex': 1})
        else:
            raise KeyError('Вы ввели неправильный пол, попробуйте ещё раз')
    # пользователь добавляет свои интересы
    if not data.get('interests'):
        data.update({'interests': str(input('Введите ваши интересы через запятую: '))})
    # пользователь добавляет своих любимых исполнителей
    if not data.get('music'):
        data.update({'music': str(input('Введите ваших любимых музыкальных исполнителей через запятую: '))})
    print('Данные пользователя получены')
    return data


# ищем матчи
def search_for_matches(user_id):
    # распознаем пол
    if get_user_data(user_id)['sex'] == 2:
        sex = 1
    elif get_user_data(user_id)['sex'] == 1:
        sex = 2
    else:
        sex = None
    # создаем диапазон возраста
    user_bdate = get_user_data(user_id)['bdate']
    user_age = int(str(datetime.date.today()).split('-')[0]) - int(user_bdate.split('.')[2])
    age_from = user_age - 3
    age_to = user_age + 3
    # сопоставляем метоположение
    city_id = get_user_data(user_id)['city']['id']
    # функция поиска
    people = requests.get('https://api.vk.com/method/users.search',
                          params=get_params({
                              'count': 1000,
                              'sort': 0,
                              'sex': sex,
                              "age_from": age_from,
                              "age_to": age_to,
                              "city": city_id,
                              "fields": "common count, interests, music, relation, bdate, status, about, activities"
                          })).json()
    print('Сбор потенциальных партнеров завершен')
    return people['response']['items']


# добавляем группы
def add_groups(user_id):
    vk_session = vk_api.VkApi(api_version='5.103',
                              token=ACCESS_TOKEN
                              )
    matches = search_for_matches(user_id)
    ids = []
    for i in matches:
        ids.append(i.get('id'))
    groups = {}
    with vk_api.VkRequestsPool(vk_session) as pool:
        for user_id in ids:
            groups[user_id] = pool.method('groups.get', {
                'user_id': user_id,
            })
    for i in matches:
        for key, value in groups.items():
            try:
                if key == i.get('id'):
                    i.update({'groups': value.result['items']})
            except vk_api.exceptions.VkRequestsPoolException:
                if key == i.get('id'):
                    i.update({'groups': 'Нет доступа к группам'})
    print('Партнерам добавлены группы')
    return matches


# скоринг
def score_matches(user_id):
    user_bdate = get_user_data(user_id)['bdate']
    user_music = get_user_data(user_id)['music']
    user_interests = get_user_data(user_id)['interests']
    user_groups = requests.get(
            'https://api.vk.com/method/groups.get',
            params=get_params({'user_id': get_user_data(user_id).get('id')}),
        ).json()['response']['items']
    data = add_groups(user_id)
    for match in data:
        score = 0
        # анализ статуса, деятельности и информации о себе на наличие сотрудничества и имейлов
        # нужно, чтобы понизить рейтинг всяких знаменитостей и рекламы, иначе приложение не эффективно
        info = f"{match.get('status')} {match.get('about')} {match.get('activities')}"
        if re.findall(r"([Сс]отруд|[Рр]еклам|[Кк]онц|[Оо]рганиз|[Сc]ъ[её]м|[Вв]опрос|[Пп]одпис|[Зз]ака|[Фф]отогр|[Гг]рупп)", info):
            score -= 10
        elif re.findall(r"\b[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b", info):
            score -= 10
        # сравниваем возраст
        match_bdate = match.get('bdate')
        if not match_bdate:
            score -= 1
        elif len(match_bdate) < 8:
            score += 0
        elif int(match_bdate.split('.')[2]) == int(user_bdate.split('.')[2]):
            score += 4
        elif int(match_bdate.split('.')[2]) - int(user_bdate.split('.')[2]) > 0:
            score += 2
        elif int(match_bdate.split('.')[2]) - int(user_bdate.split('.')[2]) < 0:
            score += 2
        # проверяем наличие отношений
        match_rel = match.get('relation')
        if not match_rel:
            score += 0
        elif match_rel in [1, 6]:
            score += 3
        elif match_rel in [2, 3, 4, 7, 8]:
            score -= 3
        elif match_rel == 5:
            score += 1
        # сравниваем музыку
        match_music = match.get('music')
        if not match_music:
            score += 0
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) == 0:
            score -= 1
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) == 1:
            score += 0.5
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) == 2:
            score += 1
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) > 2:
            score += 2
        # сравниваем интересы
        match_interests = match.get('interests')
        if not match_interests:
            score += 0
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) == 0:
            score -= 1
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) == 1:
            score += 0.5
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) == 2:
            score += 1
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) > 2:
            score += 2
        # ищем наличие общих друзей
        if not match.get('common count'):
            score += 0
        elif match.get('common count'):
            score += 2
        elif match.get('common count') > 2:
            score += 4
        # ищем совпадения в айдишниках групп
        match_groups = match.get('groups')
        if not match_groups:
            score += 0
        elif match_groups == 'Нет доступа к группам':
            score += 0
        elif len(list(set(user_groups) & set(match_groups))) == 0:
            score -= 1
        elif len(list(set(user_groups) & set(match_groups))) in range(1, 5):
            score += 1
        elif len(list(set(user_groups) & set(match_groups))) > 5:
            score += 2
        match.update({'score': score})
    print('Произведен скоринг потенциальных партнеров')
    return data


def store_to_db(user_id):
    # TODO: поискать примеры, можно ли использовать update_one с такими массивами данных,
    #  чтобы вместо недобавления было обновление полей
    data = score_matches(user_id)
    for match in data:
        if not list(b_coll.find({'id': match.get('id')})):
            b_coll.insert_one(match)
    print('Добавлено в базу')


def get_top10(user_id):
    store_to_db(user_id)
    top10 = list(b_coll.find(limit=10, projection=['id',
                                                   'first_name',
                                                   'last_name',
                                                   'score',
                                                   'bdate',
                                                   'common count',
                                                   'interests',
                                                   'music',
                                                   'relation',
                                                   'status',
                                                   'about',
                                                   'activities']).sort('score', -1))
    for match in top10:
        # удаляем поле '_id', так как оно не добавляется в json
        match.pop('_id')
        # добавляем топ 3 залайканных фото и ссылку на профиль
        photos = requests.get('https://api.vk.com/method/photos.get', params=get_params({
            'owner_id': match.get('id'),
            'album_id': 'profile',
            'extended': 1
        })).json()['response']['items']
        time.sleep(0.3)
        reworked_photos = []
        for photo in photos:
            reworked_photos.append({'owner_id': photo.get('owner_id'),
                                    'likes': (photo.get('likes')).get('count'),
                                    'url': sorted(photo.get('sizes'), key=lambda size: size.get('type'), reverse=True)[0].get('url')
                                    })
        match.update({'photo1': sorted(reworked_photos, key=lambda pic: pic.get('likes'), reverse=True)[0].get('url'),
                      'photo2': sorted(reworked_photos, key=lambda pic: pic.get('likes'), reverse=True)[1].get('url'),
                      'photo3': sorted(reworked_photos, key=lambda pic: pic.get('likes'), reverse=True)[2].get('url'),
                      'profile_url': f'https://vk.com/id{match.get("id")}'

        })
    with open('top10.json', 'w', encoding='utf-8') as f:
        json.dump(top10, f, ensure_ascii=False, indent=4)
    print('Топ10 профилей загружено в файл')
    # return top10


if __name__ == '__main__':
    # pprint(get_user_data('erezerblade'))
    # pprint(search_for_matches('erezerblade'))
    # pprint(add_groups('erezerblade'))
    # pprint(score_matches('erezerblade'))
    # store_to_db('erezerblade')
    # pprint(get_top10('erezerblade'))
    get_top10('erezerblade')
