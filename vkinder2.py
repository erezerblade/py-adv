import requests
import datetime
from pymongo import MongoClient
import time
import re
import vk_api
import json

client = MongoClient('localhost', 27017)
bitches_db = client['ticket_db']
b_coll = bitches_db.collection

ACCESS_TOKEN = str(input('Введите ключ доступа: '))
USER_DATA = {}


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
    user_groups = requests.get(
            'https://api.vk.com/method/groups.get',
            params=get_params({'user_id': data.get('id')}),
        ).json()['response']['items']
    data.update({'groups': user_groups})
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
    USER_DATA.update(data)
    return data


# ищем матчи
def search_for_matches(user_id):
    # распознаем пол
    if USER_DATA:
        data = USER_DATA
    else:
        get_user_data(user_id)
        data = USER_DATA
    if data.get('sex') == 2:
        sex = 1
    elif data.get('sex') == 1:
        sex = 2
    else:
        sex = None
    # создаем диапазон возраста
    user_bdate = data.get('bdate')
    user_age = int(str(datetime.date.today()).split('-')[0]) - int(user_bdate.split('.')[2])
    age_from = user_age - 3
    age_to = user_age + 3
    # сопоставляем метоположение
    city_id = data['city']['id']
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
# все условные конструкции приведены к одной и той же модели 4 критериев:
# 1) если в профиле партнера данных нет или к ним нет доступа, к общему счету прибавляется 0
# 2) если данные есть, но они не совпадают с пользовательскими или скрыты, к ним прибавляется low_mark
# 3) если данные есть, и по ним есть небольшие совпадения, к ним прибавляется mid_mark
# 4) если данные есть, и по ним есть точное или широкое совпадение, к ним прибавляется high_mark
# Исключениями из этой модели являются только анализ статуса и отношений.
# Первое - потому что является фильтром спамных страниц, второе - потому что вместо low_mark в случае наличия отношений
# из счета вычитается high_mark. Все переменные mark умножаются на уровень приоритета, заданный пользователем через ввод
# Можно регулировать модель скоринга, меняя значения переменных mark
def score_matches(user_id, age, rel, mus, intr, friends, groups):
    if age > 5 or age < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    if rel > 5 or rel < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    if mus > 5 or mus < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    if intr > 5 or intr < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    if friends > 5 or friends < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    if groups > 5 or groups < 1:
        raise KeyError('Можно ввести только цифры от 1 до 5')
    data = add_groups(user_id)
    user_data = USER_DATA
    user_bdate = user_data['bdate']
    user_music = user_data['music']
    user_interests = user_data['interests']
    user_groups = user_data['groups']
    high_mark = 3
    mid_mark = 2
    low_mark = 1
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
            score += 0
        elif len(match_bdate) < 8:
            score += low_mark * age
        elif int(match_bdate.split('.')[2]) == int(user_bdate.split('.')[2]):
            score += high_mark * age
        elif int(match_bdate.split('.')[2]) - int(user_bdate.split('.')[2]) > 0:
            score += mid_mark * age
        elif int(match_bdate.split('.')[2]) - int(user_bdate.split('.')[2]) < 0:
            score += mid_mark * age
        # проверяем наличие отношений
        match_rel = match.get('relation')
        if not match_rel:
            score += 0
        elif match_rel in [1, 6]:
            score += high_mark * rel
        elif match_rel in [2, 3, 4, 7, 8]:
            score -= high_mark * rel
        elif match_rel == 5:
            score += mid_mark * rel
        # сравниваем музыку
        match_music = match.get('music')
        if not match_music:
            score += 0
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) == 0:
            score += low_mark * mus
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) == 1:
            score += mid_mark * mus
        elif len(list(set(user_music.split(', ')) & set(match_music.split(', ')))) >= 2:
            score += high_mark * mus
        # сравниваем интересы
        match_interests = match.get('interests')
        if not match_interests:
            score += 0
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) == 0:
            score -= low_mark * intr
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) == 1:
            score += mid_mark * intr
        elif len(list(set(user_interests.split(', ')) & set(match_interests.split(', ')))) >= 2:
            score += high_mark * intr
        # ищем наличие общих друзей
        if not match.get('common count'):
            score += 0
        elif match.get('common count'):
            score += low_mark * friends
        elif match.get('common count') == 1:
            score += mid_mark * friends
        elif match.get('common count') >= 2:
            score += high_mark * friends
        # ищем совпадения в айдишниках групп
        match_groups = match.get('groups')
        if not match_groups:
            score += 0
        elif match_groups == 'Нет доступа к группам':
            score += 0
        elif len(list(set(user_groups) & set(match_groups))) == 0:
            score -= low_mark * groups
        elif len(list(set(user_groups) & set(match_groups))) in range(1, 5):
            score += mid_mark * groups
        elif len(list(set(user_groups) & set(match_groups))) > 5:
            score += high_mark * groups
        match.update({'score': score})
    print('Произведен скоринг потенциальных партнеров')
    return data


def get_top10(user_id):
    data = score_matches(user_id,
                         age=int(input('Оцените от 1 до 5, насколько вам важен возраст партнера: ')),
                         rel=int(input('Оцените от 1 до 5, насколько вам важны нынешние отношения партнера: ')),
                         mus=int(input('Оцените от 1 до 5, насколько вам важны музыкальные вкусы партнера: ')),
                         intr=int(input('Оцените от 1 до 5, насколько вам важны общие с партнером интересы: ')),
                         friends=int(input('Оцените от 1 до 5, насколько вам важны общие с партнером друзья: ')),
                         groups=int(input('Оцените от 1 до 5, насколько вам важны общие с партнером группы: ')))
    top10 = sorted(data, key=lambda user: user.get('score'), reverse=True)[:10]
    for match in top10:
        # удаляем поля, чтобы было красивее
        match.pop("groups")
        match.pop("is_closed")
        match.pop("can_access_closed")
        match.pop("track_code")
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
                                    'url': sorted(photo.get('sizes'),
                                                  key=lambda size: size.get('type'), reverse=True)[0].get('url')})
        try:
            match.update({'profile_url': f'https://vk.com/id{match.get("id")}',
                          'photo1': sorted(reworked_photos, key=lambda pic: pic.get('likes'),
                                           reverse=True)[0].get('url')})
        except IndexError:
            match.update({'profile_url': f'https://vk.com/id{match.get("id")}', 'photo1': 'Фото не найдено'})
        try:
            match.update({'photo2': sorted(reworked_photos, key=lambda pic: pic.get('likes'),
                                           reverse=True)[1].get('url')})
        except IndexError:
            match.update({'photo2': 'Фото не найдено'})
        try:
            match.update({'photo3': sorted(reworked_photos, key=lambda pic: pic.get('likes'),
                                           reverse=True)[2].get('url')})
        except IndexError:
            match.update({'photo3': 'Фото не найдено'})
    with open('top10.json', 'w', encoding='utf-8') as f:
        json.dump(top10, f, ensure_ascii=False, indent=4)
    print('Топ10 профилей загружено в файл')
    return top10


def store_to_db(user_id):
    get_user_data(user_id)
    data = get_top10(user_id)
    for match in data:
        if not list(b_coll.find({'id': match.get('id')})):
            b_coll.insert_one(match)
    print('Добавлено в базу')


if __name__ == '__main__':
    store_to_db(input('Введите имя пользователя или ID: '))
    # print(get_user_data('erezerblade'))

# 2cf3437ecbb82e410781b3050c3cddab55ec962056685c16bb6f490f85cdbd09a80c1d6c44e3ba3a8101d
# erezerblade
