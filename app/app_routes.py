"""Роуты, запрос к которым происходит напрямую из приватного чита
"""
from app import app, subscribers_database, cheats_database, scheduler
from flask import make_response, request
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from app.decorators import required_params
import json


online_counter_dict = {}


@app.route('/api/app/time-left/<string:cheat_id>/<string:secret_data>/', methods=["GET"])
def get_user_subscription_time_left_enc(cheat_id, secret_data):
    """Получение оставшегося времени подписки пользователя в открытом виде
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате
          - in: path
            name: secret_data
            type: string
            description: Секретный и уникальный ключ пользователя (например, HWID)

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
        return make_response({'status': 'error', 
                              'message': 'Cheat not found'}), 400
    cheat = cheats_database['cheats'].find_one(
        {'_id': ObjectId(cheat_id)})
    subscriber = subscribers_database[cheat_id].find_one(
        {'secret_data': secret_data})
    if subscriber is not None:
        # получаем разницу во времени в минутах
        minutes = int((subscriber['expire_date'] -
                      datetime.now()).total_seconds() / 60)

        json_string = json.dumps(
            {'time_left': minutes, 'secret_data': secret_data})
        if not subscriber['active']:
            json_string = json.dumps(
                {'time_left': 'inactive', 'secret_data': secret_data})
        elif subscriber['lifetime']:
            json_string = json.dumps(
                {'time_left': 'lifetime', 'secret_data': secret_data})

        return make_response(json_string)
    return make_response(
        {'status': 'error', 'message': 'Subscriber not found'}), 400


def update_online_counter(cheat_id, secret_data):
    online_counter_dict[cheat_id].remove(secret_data)


def is_job_in_job(jobs, job_id):
    return any(job_id == job.id for job in jobs)


@app.route('/api/app/online/<string:cheat_id>/', methods=["GET"])
def get_online(cheat_id):
    """Получение онлайна чита
        ---
        consumes:
          - application/json

        parameters:
          - in: path
            name: cheat_id
            type: string
            description: ObjectId чита в строковом формате


        responses:
          200:
            description: Успешный запрос
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    count = 0
    if cheat_id in online_counter_dict:
        for _ in online_counter_dict[cheat_id]:
            count += 1
    return make_response({'online': count}), 400


@app.route('/api/app/online/', methods=["POST"])
@required_params({"cheat_id": str, "secret_data": str})
def update_online():
    """Обновление онлайна чита
        ---
        consumes:
          - application/json

        parameters:
          - in: body
            name: body
            type: object
            schema:
              properties:
                cheat_id:
                  type: string
                  description: ObjectId чита в строковом формате
                secret_data:
                  type: string
                  description: Секретный и уникальный ключ пользователя (например, HWID)

        responses:
          200:
            description: Успешный запрос
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    try:
        data = request.get_json()
        cheat_id = data['cheat_id']
        secret_data = data['secret_data']
    except:
        return make_response(
            {'status': 'error', 
             'message': 'One of the parameters specified was missing or invalid'}), 400

    # схема тут такая:
    # 1. если пользователя в счётчике онлайна нет, то добавляем его. 
    # Устанавливаем ему job на удаление из счётчика через 2 минуты
    # 2. если пользователь в счётчике онлайна есть, то обновляем ему 
    # job на удаление из счётчика (откладываем на 2 минуты)
    # таким образом, если пользователь не будет подавать онлайн 
    # сигнала 2 минуты, то он удалится из счётчика
    if (
        cheat_id in subscribers_database.list_collection_names()
        and subscribers_database[cheat_id].find_one(
            {'secret_data': secret_data}
        )
        is not None
    ):
        if cheat_id not in online_counter_dict:
            online_counter_dict.update({cheat_id: [secret_data]})
        elif secret_data not in online_counter_dict[cheat_id]:
            online_counter_dict[cheat_id].append(secret_data)

        all_jobs = scheduler.get_jobs()
        if not is_job_in_job(all_jobs, secret_data):
            scheduler.add_job(id=secret_data, func=update_online_counter, trigger="date",
                              run_date=datetime.now() + timedelta(minutes=2),
                              kwargs={'cheat_id': cheat_id, 'secret_data': secret_data})
        else:
            scheduler.modify_job(
                secret_data, next_run_time=datetime.now() + timedelta(minutes=2))
    return ''
