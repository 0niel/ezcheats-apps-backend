import requests
from app import app, cheats_database, subscribers_database, DISCOURSE_API_KEY
from flask import request, make_response
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from app.decorators import required_params, token_required


@app.route('/api/subscribers/<int:user_id>/', methods=["GET"])
@token_required
def get_all_user_subscriptions(user_id):
    """Полчение информации о всех подписках на различные читы у конкретного пользователя
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: user_id
            type: integer
            description: ID пользователя на сайте

        responses:
          200:
            description: Информация о всех подписках
            schema:
              type: object
              properties:
                subscriptions:
                  type: array
                  items:
                    type: object
                    properties:
                      cheat_id:
                        type: string
                        description: ObjectId чита в строковом формате
                      subscriber:
                        $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """

    subscriptions = []
    # проходимся по всем коллекциям и ищим подписки у пользователя
    for cheat_id in subscribers_database.list_collection_names():
        subscriber = subscribers_database[cheat_id].find_one(
            {'user_id': user_id})
        if subscriber is not None:
            # нормализуем object_id, так как в json формат такое не съест
            subscriber['_id'] = str(subscriber['_id'])
            subscription_obj = {'cheat_id': cheat_id, 'subscriber': subscriber}
            subscriptions.append(subscription_obj)

    if subscriptions:
        return make_response({'subscriptions': subscriptions})

    return make_response({'status': 'error', 'message': 'Subscriptions not found'}), 400


@app.route('/api/subscribers/<string:cheat_id>/<int:user_id>/', methods=["GET"])
@token_required
def get_user_subscription_by_cheat(cheat_id, user_id):
    """Полчение информации о подписке пользователя на конкретный чит
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: user_id
            type: integer
            description: ID пользователя на сайте

        responses:
          200:
            description: Информация о подписке
            schema:
              $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    if cheat_id not in subscribers_database.list_collection_names():
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    subscriber = subscribers_database[cheat_id].find_one({'user_id': user_id})
    if subscriber is not None:
        # нормализуем object_id, так как в json формат такое не съест
        subscriber['_id'] = str(subscriber['_id'])
        return make_response(subscriber)
    return make_response({'status': 'error', 'message': 'Subscriber not found'}), 400


@app.route('/api/subscribers/', methods=["POST"])
@required_params({"cheat_id": str, "minutes": int, "user_id": int})
@token_required
def add_subscriber_or_subscription():
    """Добавление минут к подписке на приватный чит или нового подписчика, если он до этого не имел подписку
    ---
    definitions:
      AddSubscribeResult:
        type: object
        nullable: false
        properties:
          status:
            type: string
            description: ok
          expire_date:
            type: string
            description: ISO дата, которая соответствует дате, когда у пользователя кончается подписка на чит

    consumes:
      - application/json

    security:
      - ApiKeyAuth

    parameters:
      - in: body
        name: body
        type: object
        schema:
          properties:
            cheat_id:
              type: string
              required: true
              description: Строковый ObjectId чита
            minutes:
              type: integer
              required: true
              description: Количество минут, которые необходимо добавить пользователю к подписке
            user_id:
              type: integer
              required: true
              description: ID пользователя на сайте
            ip_address:
              type: string
              required: false
              description: IP адрес пользователя. Требуется указать при добавлении нового подписчика
            lifetime:
              type: boolean
              required: false
              description: Если значение True, то пользователю будет начислена бесконечная подписка

    responses:
      200:
        description: Дата окончания подписки
        schema:
          $ref: '#/definitions/AddSubscribeResult'
      400:
        schema:
          $ref: '#/definitions/Error'
    """
    try:
        data = request.get_json()
        cheat = cheats_database.cheats.find_one(
            {'_id': ObjectId(data['cheat_id'])})
        if cheat is None:
            return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

        lifetime = data['lifetime'] if 'lifetime' in data else False
        ip_address = data['ip_address'] if 'ip_address' in data else ''
        # ID пользователя на сайте
        subscriber_user_id = data['user_id']
        # ник пользователя на сайте. Используется для поиска подписчика по нику
        user_name = ''

        if DISCOURSE_API_KEY is not None:
            discourse_user_info = requests.get(
                f'https://forum.ezcheats.ru/admin/users/{subscriber_user_id}.json',
                headers={'Api-Key': DISCOURSE_API_KEY},
            ).json()

            if 'errors' in discourse_user_info:
                if 'error_type' == 'not_found':
                    return make_response({'status': 'error', 'message': 'User not found'}), 400
                else:
                    return make_response({'status': 'error', 'message': discourse_user_info['errors'][0]}), 400

            user_name = discourse_user_info['username']

        # ищем подписчика чита по его ID на сайте
        subscriber = subscribers_database[data.get('cheat_id')].find_one({
            'user_id': subscriber_user_id})

        # если пользователь уже до этого имел подписку на чит
        if subscriber is not None:
            # если пользователь уже имеет активную подписку, то просто добавляем ему время
            if (subscriber['expire_date'] - subscriber['start_date']).seconds > 0:
                expire_date = subscriber['expire_date'] + \
                    timedelta(minutes=data['minutes'])
            else:
                expire_date = datetime.now() + \
                    timedelta(minutes=data['minutes'])

            # устанавливаем новую дату окончания подписки, меняем статус на активную,
            # увеличиваем счётчик кол-ва подписок на 1
            subscribers_database[data.get('cheat_id')].update_one(
                {'_id': subscriber['_id']}, 
                {'$set': {
                    'expire_date': expire_date, 
                    'active': True, 'lifetime': lifetime
                    }, 
                 '$inc': {
                     'subscriptions_count': 1
                     }
                 })
        # пользователь ещё не имел подписки на это чит. Добавляем его
        else:
            start_date = datetime.now()
            expire_date = start_date + timedelta(minutes=data['minutes'])
            subscriber_data = {
                'user_id': subscriber_user_id, 
                'user_name': user_name, 
                'start_date': start_date,
                'expire_date': expire_date, 
                'ip_start': ip_address, 
                'ip_last': ip_address, 
                'secret_data': '',
                'last_online_date': '', 
                'subscriptions_count': 1, 
                'lifetime': lifetime, 
                'active': True
                }

            subscribers_database[data.get(
                'cheat_id')].insert_one(subscriber_data)

        return make_response({'status': 'ok', 'expire_date': expire_date})

    except:
        return make_response(
            {'status': 'error', 
             'message': 'One of the parameters specified was missing or invalid'}), 400


@app.route('/api/subscribers/<string:cheat_id>/<int:user_id>/', methods=["DELETE"])
@token_required
def delete_subscriber(cheat_id, user_id):
    """Удаление подписчика у чита по его id на сайте
    ---
    consumes:
      - application/json

    parameters:
      - in: path
        name: cheat_id
        type: string
        description: ObjectId чита в строковом формате
      - in: path
        name: user_id
        type: integer
        description: ID пользователя на сайте

    responses:
      200:
        description: Статус-код успешного удаления
        schema:
          type: object
          properties:
            status:
              type: string
              description: ok status
      400:
        schema:
          $ref: '#/definitions/Error'
    """
    try:
        cheat = cheats_database['cheats'].find_one({'_id': ObjectId(cheat_id)})

        if cheat is None:
            return make_response({'status': 'error', 
                                  'message': 'Cheat not found'}), 400

        subscriber = subscribers_database[cheat_id].find_one(
            {'user_id': user_id})

        if subscriber is None:
            return make_response({'status': 'error', 
                                  'message': 'Subscriber not found'}), 400

        subscribers_database[cheat_id].delete_one({'user_id': user_id})
        return make_response({'status': 'ok'})

    except:
        return make_response(
            {'status': 'error', 
             'message': 'One of the parameters specified was missing or invalid'}), 400


@app.route('/api/subscribers/search/<string:cheat_id>/<string:name_substring>/', methods=["GET"])
@token_required
def search_subscribers(cheat_id, name_substring):
    """Поиск подписчика на чит по ник-нейму
    ---
    consumes:
      - application/json

    parameters:
      - in: path
        name: cheat_id
        type: string
        description: ObjectId в строковом формате
      - in: path
        name: name_substring
        type: string
        description: Строка (ник-нейм), по вхождению которой ищется пользователь

    responses:
      200:
        description: ID вставленного объекта
        schema:
          type: object
          properties:
            subscribers:
              type: array
              items:
                $ref: '#/definitions/Subscriber'
      400:
        schema:
          $ref: '#/definitions/Error'
    """

    if cheat_id not in subscribers_database.list_collection_names():
        return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

    subscribers_database[cheat_id].create_index(
        [('user_name', 'text')], default_language="english")
    subscribers = []
    cursor = subscribers_database[cheat_id].find(
        {'user_name': {'$regex': name_substring, '$options': '$i'}}).limit(50)

    for document in cursor:
        document['_id'] = str(document['_id'])
        subscribers.append(document)

    return make_response({'subscribers': subscribers})


@app.route('/api/subscribers/<string:cheat_id>/<int:skip>/<int:limit>/', methods=["GET"])
@token_required
def get_all_cheat_subscribers(cheat_id, skip, limit):
    """Получение определённого кол-ва подписчиков конкретного чита, начиная с определённой позиции
        ---
        definitions:
          Subscriber:
            type: object
            properties:
              _id:
                type: string
                description: ObjectId
              user_id:
                type: integer
                description: Пользовательский ID на сайте
              user_name:
                type: string
                description: Ник пользователя на сайте
              start_date:
                type: string
                description: Дата начала подписки (дата первой активации) (ISO формат)
              expire_date:
                type: string
                description: Дата окончания подписки (ISO формат)
              ip_start:
                type: string
                description: IP, с которого проводилась первая активация подписки
              ip_last:
                type: string
                description: IP, с которого пользователь последний раз зашёл в чит
              secret_data:
                type: string
                description: Секретный и уникальный ключ пользователя, который не меняется в рамках одного ПК. Например,
                    HWID + соль в зашифрованном виде
              last_online_date:
                type: string
                description: Дата последнего захода в чит (ISO формат)
              subscriptions_count:
                type: integer
                description: Количество активаций подписки
              lifetime:
                type: boolean
                description: Имеет ли пользователь бесконечную подписку. Если True, то expire_date не важна
              active:
                type: boolean
                description: Активная ли подписка у пользователя или приостановлена. Не используется для проверки
                    подписки в чите, только для проверки её активности. Если False, то считаем, что пользователь на
                    данный момент подписку не имеет, если True, то проверяем lifetime и expire_date

        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: skip
            type: integer
            description: Позиция, с которой начать выборку подписчиков. Если 0, то будут выбраны все с начала
          - in: path
            name: limit
            type: integer
            description: Количество подписчиков для выборки

        responses:
          200:
            description: Список подписчиков по выборке
            schema:
              type: object
              properties:
                subscribers:
                  type: array
                  items:
                    $ref: '#/definitions/Subscriber'
          400:
            schema:
              $ref: '#/definitions/Error'
    """

    # skip - позиция, с которой начинаем выборку
    # limit - кол-во элементов для выборки
    cursor = subscribers_database[cheat_id].find({}).skip(skip).limit(limit)
    subscribers = []
    for document in cursor:
        # нормализуем ObjectId
        document['_id'] = str(document['_id'])
        subscribers.append(document)
    return make_response({'subscribers': subscribers})
