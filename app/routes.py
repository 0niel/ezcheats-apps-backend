from app import app, cheats_database, subscribers_database
from flask import Flask, flash, request, redirect, url_for, session, jsonify, render_template, make_response, Response
from functools import wraps
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


def required_params(required):
    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            _json = request.get_json()
            missing = [r for r in required.keys()
                       if r not in _json]
            if missing:
                response = {
                    "status": "error",
                    "message": "Request JSON is missing some required params",
                    "missing": missing
                }
                return jsonify(response), 400
            wrong_types = [r for r in required.keys()
                           if not isinstance(_json[r], required[r])]
            if wrong_types:
                response = {
                    "status": "error",
                    "message": "Data types in the request JSON doesn't match the required format",
                    "param_types": {k: str(v) for k, v in required.items()}
                }
                return jsonify(response), 400
            return fn(*args, **kwargs)

        return wrapper

    return decorator


@app.route('/api/subscribers/', methods=["POST"])
@required_params({"cheat_id": str, "minutes": int, "user_id": int})
def add_subscriber_or_subscription():
    try:
        data = request.get_json()
        cheat = cheats_database.cheats.find_one({'_id': ObjectId(data['cheat_id'])})
        if cheat is None:
            return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

        # ID пользователя на сайте
        subscriber_user_id = data['user_id']

        # ищем подписчика чита по его ID на сайте
        subscriber = subscribers_database[data.get('cheat_id')].find_one({'user_id': subscriber_user_id})

        # если пользователь уже до этого имел подписку на чит
        if subscriber is not None:
            # если пользователь уже имеет активную подписку, то просто добавляем ему время
            if (subscriber['expire_date'] - subscriber['start_date']).seconds > 0:
                expire_date = subscriber['expire_date'] + timedelta(minutes=data['minutes'])
            else:
                expire_date = datetime.now() + timedelta(minutes=data['minutes'])

            subscribers_database[data.get('cheat_id')].update_one({'_id': subscriber['_id']},
                                                                  {'$set': {'expire_date': expire_date}})
        # пользователь ещё не имел подписки на это чит. Добавляем его
        else:
            start_date = datetime.now()
            expire_date = start_date + timedelta(minutes=data['minutes'])
            subscriber_data = {'user_id': subscriber_user_id, 'start_date': start_date, 'expire_date': expire_date,
                               'ip_start': '', 'ip_last': '', 'secret_data': '', 'last_online_date': '',
                               'subscriptions_count': 1, 'active': True}

            subscribers_database[data.get('cheat_id')].insert_one(subscriber_data)

        return make_response({'status': 'ok', 'expire_date': expire_date})

    except:
        return make_response(
            {'status': 'error', 'message': 'One of the parameters specified was missing or invalid'}), 400


@app.route('/api/cheats/', methods=["POST"])
@required_params({"title": str, "owner_id": int, "version": str})
def create_new_cheat():
    """Создание нового приватного чита
    ---
    definitions:
      Error:
        type: object
        properties:
          status:
            type: string
            description: Error status
          message:
            type: string

      ObjectId:
        type: object
        nullable: false
        properties:
          object_id:
            type: string
            description: Уникальный ID (hex формата) созданного объекта в базе данных

    consumes:
      - application/json

    parameters:
      - in: header
        name: X-Auth-Token
        type: string
        required: true
      - in: body
        name: title
        type: string
        required: true
      - in: body
        name: owner_id
        type: integer
        required: true
      - in: body
        name: version
        type: string
        required: true

    responses:
      200:
        description: ID вставленного объекта
        schema:
          $ref: '#/definitions/ObjectId'
      400:
        schema:
          $ref: '#/definitions/Error'
      503:
          description: Retry-After:100
    """

    data = request.get_json()
    title = data['title']
    owner_id = data['owner_id']
    version = data['version']

    cheat = cheats_database.cheats.find_one({'title': title, 'owner_id': owner_id})
    if cheat is not None:
        return make_response({'status': 'error', 'message': 'Cheat already exists'}), 400
    else:
        # статусы чита:
        # working - работает, on_update - на обновлении, stopped - остановлен

        # секретный ключ чита, который используется при AES шифровании
        secret_key = get_random_bytes(16)  # Генерируем ключ шифрования

        object_id = str(cheats_database.cheats.insert_one({
            "title": title, 'owner_id': owner_id, 'version': version, 'subscribers': 0,
            'subscribers_for_all_time': 0, 'subscribers_today': 0, 'undetected': True,
            'created_date': datetime.now(), 'updated_date': datetime.now(), 'status': 'working',
            'secret_key': secret_key
        }).inserted_id)

    return make_response({'status': 'ok', 'object_id': object_id})
