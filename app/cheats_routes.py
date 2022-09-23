from app import app, cheats_database, subscribers_database
from flask import request, make_response
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from Crypto.Cipher import AES
from app.decorators import required_params, token_required
import string
import random


@app.route('/api/cheats/', methods=["POST"])
@required_params({"title": str, "owner_id": int, "version": str})
@token_required
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
          status:
            type: string
            description: ok
          object_id:
            type: string
            description: Уникальный ID (hex формата) созданного объекта в базе данных

    consumes:
      - application/json

    parameters:
      - in: body
        name: body
        type: object
        schema:
          properties:
            title:
              type: string
              description: Название приватного чита
            owner_id:
              type: integer
              description: ID пользователя на сайте
            version:
              type: string

    responses:
      200:
        description: ID вставленного объекта
        schema:
          $ref: '#/definitions/ObjectId'
      400:
        schema:
          $ref: '#/definitions/Error'
    """

    data = request.get_json()
    title = data['title']
    owner_id = data['owner_id']
    version = data['version']

    cheat = cheats_database.cheats.find_one(
        {'title': title, 'owner_id': owner_id})
    if cheat is not None:
        return make_response({'status': 'error', 'message': 'Cheat already exists'}), 400
    # статусы чита:
    # working - работает, on_update - на обновлении, stopped - остановлен

    # секретный ключ чита, который используется при AES шифровании
    # Генерируем ключ шифрования
    letters_and_digits = string.ascii_letters + string.digits
    secret_key = ''.join(random.sample(letters_and_digits, 16))

    object_id = str(cheats_database.cheats.insert_one({
        'title': title, 'owner_id': owner_id, 'version': version, 
        'subscribers': 0, 'subscribers_for_all_time': 0, 
        'subscribers_today': 0, 'undetected': True, 
        'created_date': datetime.now(), 'updated_date': datetime.now(),
        'status': 'working', 'secret_key': secret_key
    }).inserted_id)

    return make_response(
        {'status': 'ok', 'object_id': object_id, 'secret_key': secret_key}
    )


@app.route('/api/cheats/', methods=["GET"])
def get_all_cheats():
    """Получения списка всех читов
        ---
        definitions:
          Cheat:
            type: object
            properties:
              _id:
                type: string
                description: ObjectId
              title:
                type: string
                description: Название чита
              owner_id:
                type: integer
                description: Пользовательский ID владельца на сайте
              version:
                type: string
                description: Строковая версия чита
              subscribers:
                type: integer
                description: Количество подписчиков с активной подпиской
              subscribers_for_all_time:
                type: integer
                description: Количество подписчиков за всё время
              subscribers_today:
                type: integer
                description: Количество новых подписчиков сегодня
              undetected:
                type: boolean
                description: Статус обнаружения чита античитом
              created_date:
                type: string
                description: Дата добавления чита (ISO формат)
              updated_date:
                type: string
                description: Дата последнего обновления чита (ISO формат)
              status:
                type: string
                description: Статус чита. working - работает, on_update - на обновлении, stopped - остановлен

        consumes:
          - application/json

        responses:
          200:
            description: Полный список приватных читов
            schema:
              type: object
              properties:
                cheats:
                  type: array
                  items:
                    $ref: '#/definitions/Cheat'
          400:
            schema:
              $ref: '#/definitions/Error'
    """
    cursor = cheats_database['cheats'].find({})
    cheats = []
    for document in cursor:
        # нормализуем ObjectId
        document['_id'] = str(document['_id'])
        # удаляем приватные данные:
        del document['secret_key']
        cheats.append(document)
    return make_response({'cheats': cheats})


@app.route('/api/cheats/<string:cheat_id>/', methods=["DELETE"])
@token_required
def delete_cheat_by_id(cheat_id):
    """Удаление чита по его ObjectId и коллекцию подписчиков на чит
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
            return make_response({'status': 'error', 'message': 'Cheat not found'}), 400

        cheats_database['cheats'].delete_one({'_id': ObjectId(cheat_id)})
        subscribers_database[cheat_id].remove()
        subscribers_database[cheat_id].drop()

        return make_response({'status': 'ok'})
    except:
        return make_response(
            {'status': 'error', 
             'message': 'One of the parameters specified was missing or invalid'}), 400
