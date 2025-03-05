from flask import Flask, request, jsonify, render_template
import mysql.connector

app = Flask(__name__)

def connecter_db():
    return mysql.connector.connect(
        host="localhost",
        user="MatarCoume",
        password="passer",
        database="smarttech"
    )

@app.route('/')
def home():
    return render_template('smarttech.html')  # Afficher l'interface web

@app.route('/api/<table>', methods=['GET'])
def lire_donnees(table):
    conn = connecter_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table}")
    resultats = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(resultats)

@app.route('/api/<table>/<int:id>', methods=['GET'])
def lire_une_donnee(table, id):
    conn = connecter_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (id,))
    resultat = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(resultat)

@app.route('/api/<table>', methods=['POST'])
def creer_donnee(table):
    conn = connecter_db()
    cursor = conn.cursor()
    data = request.json
    
    colonnes = ', '.join(data.keys())
    valeurs = tuple(data.values())
    placeholders = ', '.join(['%s'] * len(valeurs))
    
    query = f"INSERT INTO {table} ({colonnes}) VALUES ({placeholders})"
    cursor.execute(query, valeurs)
    conn.commit()
    
    cursor.close()
    conn.close()
    return jsonify({"message": "Donnée ajoutée avec succès!"})

@app.route('/api/<table>/<int:id>', methods=['PUT'])
def mettre_a_jour_donnee(table, id):
    conn = connecter_db()
    cursor = conn.cursor()
    data = request.json

    print("Données reçues pour mise à jour:", data)  # Ajoute cette ligne

    set_clause = ', '.join([f"{col} = %s" for col in data.keys()])
    valeurs = tuple(data.values()) + (id,)

    query = f"UPDATE {table} SET {set_clause} WHERE id = %s"
    
    try:
        cursor.execute(query, valeurs)
        conn.commit()
        return jsonify({"message": "Mise à jour réussie!"})
    except Exception as e:
        print("Erreur SQL:", e)  # Affiche l'erreur SQL
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/<table>/<int:id>', methods=['DELETE'])
def supprimer_donnee(table, id):
    conn = connecter_db()
    cursor = conn.cursor()
    query = f"DELETE FROM {table} WHERE id = %s"
    cursor.execute(query, (id,))
    conn.commit()
    
    cursor.close()
    conn.close()
    return jsonify({"message": "Suppression réussie!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

