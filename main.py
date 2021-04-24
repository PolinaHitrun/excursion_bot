from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler, ConversationHandler
from telegram import ReplyKeyboardMarkup
import sqlite3
import requests

TOKEN = '1677372076:AAHAfzDzY0oWgxYyVZOiffUmpmHEyzEZ4ww'
# базовая клавиатура бота
reply_keyboard = [['/create_excursion', '/help', '/excursions'], ['/rename_excursion', '/delete_excursion']]
markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False)

# ОСНОВНЫЕ ФУНКЦИИ


def start(update, context):
    """Приветствует пользователя и добавляет нового в бд"""
    # информация о пользователе
    user = update.message.from_user
    # подключение к базе данных
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # добавление нового пользователя бота в бд
    try:
        cur.execute("""INSERT INTO users(username) VALUES(?)""", (user['username'], )).fetchall()
    except sqlite3.IntegrityError:
        pass
    # приветствие
    update.message.reply_text(f'Привет, {user["first_name"]}! '
                              f'Я могу составить экскурсию, а потом провести по ней. Отправь команду',
                              reply_markup=markup)
    con.commit()


def help(update, context):
    """Рассказывает, как пользоваться ботом"""
    update.message.reply_text('Что я умею? \n'
                              '/create_excursion начните создавать экскурсию, вводя названия мест одно за другим. Чтобы закончить, отправьте /stop \n'
                              '/excursions посмотреть список своих экскурсий и выбрать одну для прогулки \n'
                              '/rename_excursion переименовать экскурсию \n'
                              '/delete_excursion удалить одну из экскурсий\n')


def show_list_to_delete(update, context):
    """Показывает список экскурсий для удаления"""
    # информация о пользователе
    user = update.message.from_user
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # получение списка экскурсий этого пользователя
    res = cur.execute("""SELECT name FROM ways WHERE user_id = (SELECT id FROM users WHERE username = ?)""",
                      (user['username'],)).fetchall()
    # клавиатура со всеми экскурсиями
    keyboard = [[i[0] for i in res]]
    mark = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    update.message.reply_text('Выбери экскурсию для удаления', reply_markup=mark)
    return 'delete'


def delete(update, context):
    """Удаляет экскурсию"""
    # имя удаляемой экскурсии
    name = update.message.text
    # информация о пользователе
    user = update.message.from_user
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # удаление
    cur.execute("""DELETE from ways WHERE name = ? 
    and user_id = (SELECT id FROM users where username = ?)""", (name, user['username'])).fetchall()
    update.message.reply_text('Удалил', reply_markup=markup)
    con.commit()
    return -1


def show_list_to_update(update, context):
    """Показывает список экскурсий для переименования"""
    # информация о пользователе
    user = update.message.from_user
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # список экскурсий этого пользователя
    res = cur.execute("""SELECT name FROM ways WHERE user_id = (SELECT id FROM users WHERE username = ?)""",
                      (user['username'],)).fetchall()
    # клавиатура с экскурсиями
    keyboard = [[i[0] for i in res]]
    mark = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    update.message.reply_text('Выбери экскурсию для переименования', reply_markup=mark)
    return 'ask'


def ask(update, context):
    """Запрашивает новое имя"""
    context.user_data['old_name'] = update.message.text
    update.message.reply_text('Придумайте новое имя')
    return 'rename'


def rename(update, context):
    """Изменяет имя экскурсии в бд"""
    new_name = update.message.text
    # информация о пользователе
    user = update.message.from_user
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # изменение имени
    cur.execute("""UPDATE ways 
                    SET name = ?
                    WHERE name = ? 
                    and user_id = (SELECT id FROM users where username = ?)""",
                (new_name, context.user_data['old_name'], user['username'])).fetchall()
    update.message.reply_text('Готово!', reply_markup=markup)
    con.commit()
    return -1

# СОЗДАНИЕ ЭКСКУРСИИ


def stop_creating(update, context):
    return -1


def name(update, context):
    """Запрашивает имя новой экскурсии"""
    update.message.reply_text('Как назовём экскурсию?')
    return 'create'


def create_excursion(update, context):
    """Запрашивает название места и начинает создание экскурсии"""
    # сохранение названия
    context.user_data['name'] = update.message.text
    update.message.reply_text('Напишите место')
    # здесь будет храниться экскурсия
    context.user_data['way'] = ''
    return 'get_place'


def if_add_place(update, context):
    """Присылает картинку и спрашивает, надо ли добавлять это место"""
    if update.message.text == '/stop':
        # если пользователь останавливает создание маршрута
        # информация о пользователе
        user = update.message.from_user
        # подключение к бд
        con = sqlite3.connect('excursions.db')
        cur = con.cursor()
        # внесение новой экскурсии в бд
        cur.execute("""INSERT INTO ways(name,places,user_id) VALUES(?,?,(SELECT id FROM users WHERE username = ?))""",
                    (context.user_data['name'], context.user_data['way'], user['username']))
        con.commit()
        # создание запроса к static maps api
        req = make_request(context.user_data['way'])
        # отправляю фото
        context.bot.send_photo(
            update.message.chat_id,
            req,
        )
        update.message.reply_text('Держи маршрут', reply_markup=markup)
        # завершение диалога
        return -1
    # сохранение названия новой точки
    context.user_data['place_name'] = update.message.text
    # номер объекта среди запросов
    context.user_data['index'] = 0
    # запрос к геокодеру
    geocoder_request = f"http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode={context.user_data['place_name']}&format=json"
    response = requests.get(geocoder_request)
    json_response = response.json()
    # обработка пустого запроса
    try:
        toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][context.user_data['index']]["GeoObject"]
    except IndexError:
        update.message.reply_text('Я не знаю такого места')
        return None
    # название места
    address = toponym["metaDataProperty"]["GeocoderMetaData"]["text"]
    # координаты места
    coodrinates = ','.join(toponym["Point"]["pos"].split())
    # получаю и отправляю картинку запрашиваемого места
    static_api_request = f"http://static-maps.yandex.ru/1.x/?ll={coodrinates}&spn=0.01,0.01&l=sat"
    context.bot.send_photo(
        update.message.chat_id,
        static_api_request,
        caption=address
    )
    # клавиатура ответов
    keyboard = [['Да', 'Нет']]
    mark = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    update.message.reply_text('Добавить это место в маршрут?', reply_markup=mark)
    return 'yes_no'


def adding(update, context):
    """Добавляю место в маршрут"""
    if update.message.text == '/stop':
        # если пользователь останавливает создание маршрута
        # информация о пользователе
        user = update.message.from_user
        # подключение к бд
        con = sqlite3.connect('excursions.db')
        cur = con.cursor()
        # внесение новой экскурсии в бд
        cur.execute("""INSERT INTO ways(name,places,user_id) VALUES(?,?,(SELECT id FROM users WHERE username = ?))""",
                    (context.user_data['name'], context.user_data['way'], user['username']))
        con.commit()
        # создание запроса к static maps api
        req = make_request(context.user_data['way'])
        # отправляю фото
        context.bot.send_photo(
            update.message.chat_id,
            req,
        )
        update.message.reply_text('Держи маршрут', reply_markup=markup)
        # завершение диалога
        return -1

    # пользователь хочет сохранить это место
    if update.message.text == 'Да':
        # дополняю строку с маршрутом новым местом
        context.user_data['way'] += context.user_data['place_name'] + ':' + str(context.user_data['index']) + ';'
        update.message.reply_text('Сохранил. Напишите название следующего места')
        # запрашиваю следующую точку
        return 'get_place'
    # пользователь хочет увидеть следующий результат по запросу
    elif update.message.text == 'Нет':
        update.message.reply_text('Может это?')
        # прибавляю номер запроса
        context.user_data['index'] += 1
        # запрос к геокодеру
        geocoder_request = f"http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode={context.user_data['place_name']}&format=json"
        response = requests.get(geocoder_request)
        json_response = response.json()
        # обработка закончившихся запросов
        try:
            toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][context.user_data['index']]["GeoObject"]
        except IndexError:
            update.message.reply_text('Я больше не знаю таких мест', reply_markup=markup)
            # завершение диалога
            return -1
        # название места
        address = toponym["metaDataProperty"]["GeocoderMetaData"]["text"]
        # координаты
        coodrinates = ','.join(toponym["Point"]["pos"].split())
        # запрашиваю и отправляю картинку с местом
        static_api_request = f"http://static-maps.yandex.ru/1.x/?ll={coodrinates}&spn=0.01,0.01&l=sat"
        context.bot.send_photo(
            update.message.chat_id,
            static_api_request,
            caption=address
        )
        return None
    else:
        # если пользователь пишет что-то непредусмотренное
        update.message.reply_text('Я не понимаю')
        return None

# ВЫБОР ЭКСКУРСИИ


def show_list_to_walk(update, context):
    """Показывает список экскурсий"""
    # информация о пользователе
    user = update.message.from_user
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # список всех маршрутов текущего пользователя
    res = cur.execute("""SELECT name FROM ways WHERE user_id = (SELECT id FROM users WHERE username = ?)""", (user['username'], )).fetchall()
    # клавиатура со всеми экскурсиями
    keyboard = [[i[0] for i in res]]
    mark = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    update.message.reply_text('Выбери экскурсию', reply_markup=mark)
    return 'walking'


def walk(update, context):
    # название выбранной экскурсии
    ex_name = update.message.text
    context.user_data['ex_name'] = ex_name
    username = update.message.from_user['username']
    # подключение к бд
    con = sqlite3.connect('excursions.db')
    cur = con.cursor()
    # обработка некорректного ввода
    try:
        # запрашиваю маршрут по названию
        places = cur.execute("""SELECT places FROM ways 
        WHERE user_id = (SELECT id FROM users WHERE username = ?) and name = ?""",
                        (username, ex_name)).fetchall()[0][0]
    except IndexError:
        update.message.reply_text('Такой экскурсии нет')
        # ожидаю корректного ввода
        return None
    # список всех мест
    context.user_data['places'] = places[:-1].split(';')
    # клавиатура с ответом
    mark = ReplyKeyboardMarkup([['Да', 'Нет']], one_time_keyboard=True)
    # запрос к static maps api
    req = make_request(places)
    # отправляю фото
    context.bot.send_photo(
        update.message.chat_id,
        req
    )
    update.message.reply_text('Хотите прогуляться по маршруту ' + ex_name, reply_markup=mark)
    # перехожу к прогулке
    return 'show_place'


def show_place(update, context):
    """Показывает точку маршрута"""
    message = update.message.text
    # пользователь продолжает прогулку
    if 'да' in message.lower():
        # если места в экскурсии закончились
        if not context.user_data['places']:
            # завершение экскурсии
            update.message.reply_text('На этом экскурсия закончена', reply_markup=markup)
            return -1
        # ещё есть точки
        else:
            # забираю следующее место из списка
            place = context.user_data['places'].pop(0)
            place, index = place.split(':')
            # запрос к геокодеру
            geocoder_request = f"http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode={place}&format=json"
            response = requests.get(geocoder_request)
            json_response = response.json()
            # получение места с нужным названием и нужным индексом
            toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][int(index)]["GeoObject"]
            address = toponym["metaDataProperty"]["GeocoderMetaData"]["text"]
            coodrinates = ','.join(toponym["Point"]["pos"].split())
            # получение и отправка фото места
            static_api_request = f"http://static-maps.yandex.ru/1.x/?ll={coodrinates}&spn=0.01,0.01&l=sat"
            context.bot.send_photo(
                update.message.chat_id,
                static_api_request,
                caption=address
            )
            update.message.reply_text('Перейти к следующей локации?')
            return None
    # пользователь завершает прогулку
    elif 'нет' in message.lower():
        update.message.reply_text('Ну и ладно', reply_markup=markup)
        return -1
    # обработка некорректного ввода
    else:
        update.message.reply_text('Я не понимаю')
        return None


def make_request(places):
    request = f'https://static-maps.yandex.ru/1.x/?l=sat&pt='
    place_list = places[:-1].split(';')
    for i in range(len(place_list)):
        name, index = place_list[i].split(':')
        geocoder_request = f"http://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&geocode={name}&format=json"
        response = requests.get(geocoder_request)
        json_response = response.json()
        toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][int(index)]["GeoObject"]
        coodrinates = ','.join(toponym["Point"]["pos"].split())
        request += coodrinates + ',' + str(i + 1) + '~'
    return request[:-1]


def main():
    updater = Updater(TOKEN, use_context=True)

    dp = updater.dispatcher

    # диалог для создания экскурсии
    creating_handler = ConversationHandler(
        entry_points=[CommandHandler('create_excursion', name)],
        states={
            'create': [MessageHandler(Filters.text, create_excursion, pass_user_data=True)],
            'get_place': [MessageHandler(Filters.text, if_add_place, pass_user_data=True)],
            'yes_no': [MessageHandler(Filters.text, adding, pass_user_data=True)]
        },
        fallbacks=[CommandHandler('stop', stop_creating)],
        allow_reentry=True
    )

    # диалог для прогулки
    exc_list_handler = ConversationHandler(
        entry_points=[CommandHandler('excursions', show_list_to_walk)],
        states={
            'walking': [MessageHandler(Filters.text, walk, pass_user_data=True)],
            'show_place': [MessageHandler(Filters.text, show_place, pass_user_data=True)]
        },
        fallbacks=[CommandHandler('stop', stop_creating)],
        allow_reentry=True
    )

    # диалог для удаления
    delete_excursion = ConversationHandler(
        entry_points=[CommandHandler('delete_excursion', show_list_to_delete)],
        states={
            'delete': [MessageHandler(Filters.text, delete, pass_user_data=True)]
        },
        fallbacks=[CommandHandler('stop', stop_creating)]
    )

    # диалог для переименования
    update_excursion = ConversationHandler(
        entry_points=[CommandHandler('rename_excursion', show_list_to_update)],
        states={
            'ask': [MessageHandler(Filters.text, ask, pass_user_data=True)],
            'rename': [MessageHandler(Filters.text, rename, pass_user_data=True)]
        },
        fallbacks=[CommandHandler('stop', stop_creating)]
    )

    # добавляю все хэндлеры
    dp.add_handler(creating_handler)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(exc_list_handler)
    dp.add_handler(delete_excursion)
    dp.add_handler(update_excursion)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()