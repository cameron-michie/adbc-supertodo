from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import logging
import os
import json
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_db_connection():
    conn = psycopg2.connect(dbname='supertododemo', 
                            user='postgres', 
                            password='mysecretpassword', 
                            host='database-yes.cl4wq0g84wtc.eu-north-1.rds.amazonaws.com', 
                            port='5432')
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS todos (
            id SERIAL PRIMARY KEY,
            task TEXT,
            completed BOOLEAN NOT NULL,
            id INT NOT NULL REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS outbox (
            sequence_id  serial PRIMARY KEY,
            mutation_id  TEXT NOT NULL,
            channel      TEXT NOT NULL,
            name         TEXT NOT NULL,
            rejected     boolean NOT NULL DEFAULT false,
            data         JSONB,
            headers      JSONB,
            locked_by    TEXT,
            lock_expiry  TIMESTAMP WITHOUT TIME ZONE,
            processed    BOOLEAN NOT NULL DEFAULT false
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def write_to_outbox(action, item):

    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
        INSERT INTO outbox (mutation_id, channel, name, data, headers)
        VALUES (%s, %s, %s, %s, %s)
    """
    # Convert `item` dictionary to a JSON string
    item_json = json.dumps(item)

    values = ("my_mutation_id", 'todos', action, item_json, item_json)

    try:
        cur.execute(query, values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Failed to write to outbox", exc_info=e)
    finally:
        cur.close()
        conn.close()

def upsert_todo(item):
    conn = get_db_connection()
    cur = conn.cursor()

    # Get or create user
    cur.execute('''
        INSERT INTO users (username) VALUES (%s)
        ON CONFLICT (username) DO UPDATE SET username=EXCLUDED.username
        RETURNING id
    ''', (item['username'],))

    action = 'update' if item.get('id') else 'create'

    if item.get('id'):
        cur.execute('''
            UPDATE todos
            SET task = %s, completed = %s
            WHERE id = %s
        ''', (item['task'], item['completed'], item['id']))
    else:
        cur.execute('''
            INSERT INTO todos (task, completed) VALUES (%s, %s) 
            RETURNING id
        ''', (item['task'], item['completed']))
        item['id'] = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    write_to_outbox(action, item)

def delete_todo(id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        SELECT id, task, completed FROM todos
        WHERE id = %s
    ''', (id,))
    item = cur.fetchone()

    if not item:
        cur.close()
        conn.close()
        return

    # Use index access for item as it's a tuple returned by fetchone()
    item_data = {
        "id": item[0],
        "task": item[1],
        "completed": item[2],
        "username": "Anonymous delete"  # Use the placeholder username
    }

    cur.execute('DELETE FROM todos WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()

    write_to_outbox('delete', item_data)

def get_todos(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT todos.id, todos.task, todos.completed, users.username
        FROM todos
        JOIN users ON todos.id = users.id
        WHERE users.username = %s
        ORDER BY todos.id
    ''', (username,))
    todos = cur.fetchall()
    cur.close()
    conn.close()

    return [{'id': row[0], 'task': row[1], 'completed': row[2], 'username': row[3]} for row in todos]

with app.app_context():
    init_db()

@app.route('/api/todos', methods=['GET'])
def handle_get_todos():
    username = request.args.get('username')
    todos = get_todos(username)
    return jsonify(todos)

@app.route('/api/todos', methods=['POST'])
@app.route('/api/todos', methods=['PUT'])
def handle_upsert_todo():
    item = request.json
    if not item:
        return 'Bad Request', 400
    upsert_todo(item)
    return jsonify(item), 200

@app.route('/api/todos', methods=['DELETE'])
def handle_delete_todo():
    id = request.args.get('id')
    if not id:
        return 'Bad Request', 400
    try:
        delete_todo(int(id))
    except ValueError:
        return 'Bad Request', 400
    return '', 204

@app.route('/api/todos/initial', methods=['GET'])
def handle_get_initial_todos():
    def get_initial_todos():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT todos.id, todos.task, todos.completed, users.username
            FROM todos
            JOIN users ON todos.id = users.id
            ORDER BY todos.id
        ''')
        todos = cur.fetchall()
        cur.close()
        conn.close()

        return [{'id': row[0], 'task': row[1], 'completed': row[2], 'username': row[3]} for row in todos]

    return jsonify(get_initial_todos())

if __name__ == '__main__':
    app.run(debug=True, port=8000)
