from flask import Flask, request, jsonify, render_template
import mysql.connector
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import hashlib
import base64
import os
import threading
import time

app = Flask(__name__)

# 🔹 Configuration des bases de données
DB_CONFIG = {
    "smarttech": {
        "host": "localhost",
        "user": "MatarCoume",
        "password": "passer",
        "database": "smarttech"
    },
    "vmail": {
        "host": "localhost",
        "user": "MatarCoume",
        "password": "passer",
        "database": "vmail"
    },
    "roundcubemail": {
        "host": "localhost",
        "user": "MatarCoume",
        "password": "passer",
        "database": "roundcubemail"
    }
}

# 🔹 Configuration de l'email
EMAIL_CONFIG = {
    "host": "mail.smarttech.sn",
    "port": 587,
    "address": "postmaster@ucad.sn",
    "password": "coume090603"
}

# 🔹 Connexion à une base de données spécifique
def connecter_db(nom_db):
    return mysql.connector.connect(**DB_CONFIG[nom_db])

# 🔹 Hachage du mot de passe (pour la création d'utilisateurs)
def hacher_mot_de_passe(mot_de_passe):
    salt = base64.b64encode(hashlib.sha256().digest()).decode('utf-8')[:16]
    hachage = hashlib.sha512((mot_de_passe + salt).encode()).hexdigest()
    return f"{{SSHA512}}{hachage}{salt}"

# 🔹 Envoyer un email
def envoyer_email(destinataire, sujet, contenu):
    message = MIMEMultipart()
    message["From"] = EMAIL_CONFIG["address"]
    message["To"] = destinataire
    message["Subject"] = sujet
    message.attach(MIMEText(contenu, "plain"))

    try:
        with smtplib.SMTP(EMAIL_CONFIG["host"], EMAIL_CONFIG["port"]) as serveur:
            serveur.starttls()
            serveur.login(EMAIL_CONFIG["address"], EMAIL_CONFIG["password"])
            serveur.sendmail(EMAIL_CONFIG["address"], destinataire, message.as_string())
        print(f"✅ E-mail envoyé à {destinataire}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")

# 🔹 Créer un compte email pour un employé
def creer_compte_email(email, mot_de_passe):
    try:
        # Connexion à la base de données vmail
        conn_vmail = connecter_db("vmail")
        cursor_vmail = conn_vmail.cursor()

        # Vérifier si l'utilisateur existe déjà
        cursor_vmail.execute("SELECT username FROM mailbox WHERE username = %s", (email,))
        if cursor_vmail.fetchone():
            print(f"❌ Le compte email {email} existe déjà.")
            return

        # Hachage du mot de passe
        mot_de_passe_hache = hacher_mot_de_passe(mot_de_passe)

        # Insertion dans mailbox
        nom_utilisateur = email.split('@')[0]
        domaine_utilisateur = email.split('@')[1]
        maildir = f"{domaine_utilisateur}/{nom_utilisateur}/"
        cursor_vmail.execute(
            "INSERT INTO mailbox (username, password, name, language, maildir, domain) VALUES (%s, %s, %s, %s, %s, %s)",
            (email, mot_de_passe_hache, nom_utilisateur, 'fr_FR', maildir, domaine_utilisateur)
        )
        conn_vmail.commit()
        cursor_vmail.close()
        conn_vmail.close()

        # Connexion à la base de données roundcubemail
        conn_roundcube = connecter_db("roundcubemail")
        cursor_roundcube = conn_roundcube.cursor()

        # Insertion dans users
        cursor_roundcube.execute(
            "INSERT INTO users (username, mail_host, created) VALUES (%s, %s, NOW())",
            (email, domaine_utilisateur)
        )
        conn_roundcube.commit()

        # Récupérer l'user_id
        cursor_roundcube.execute("SELECT user_id FROM users WHERE username = %s", (email,))
        user_id = cursor_roundcube.fetchone()[0]

        # Insertion dans identities
        cursor_roundcube.execute(
            "INSERT INTO identities (user_id, changed, del, standard, name, organization, email, `reply-to`, bcc, signature, html_signature) "
            "VALUES (%s, NOW(), 0, 1, %s, '', %s, '', '', NULL, 0)",
            (user_id, nom_utilisateur, email)
        )
        conn_roundcube.commit()
        cursor_roundcube.close()
        conn_roundcube.close()

        print(f"✅ Compte email créé pour {email}")
    except mysql.connector.Error as e:
        print(f"❌ Erreur lors de la création du compte email : {e}")

# 🔹 Surveillance de répertoire
class SurveilleurFTP(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            fichier = event.src_path
            # Ignorer les fichiers temporaires (.filepart)
            if fichier.endswith('.filepart'):
                return

            print(f"📂 Nouveau fichier détecté : {fichier}")
            employe = choisir_employe()
            if employe:
                enregistrer_fichier(fichier, employe['id'])
                envoyer_email(employe['email'], "Nouveau fichier assigné", f"Un nouveau fichier vous a été assigné : {fichier}")

def choisir_employe():
    conn = connecter_db("smarttech")
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nom, prenom, email FROM employe")
    employes = cursor.fetchall()
    cursor.close()
    conn.close()

    print("Sélectionnez un employé pour ce fichier :")
    for emp in employes:
        print(f"{emp['id']}: {emp['prenom']} {emp['nom']} ({emp['email']})")
    
    emp_id = int(input("Entrez l'ID de l'employé : "))
    employe = next((e for e in employes if e['id'] == emp_id), None)
    return employe

def enregistrer_fichier(fichier, employe_id):
    conn = connecter_db("smarttech")
    cursor = conn.cursor()
    query = "INSERT INTO documents (nom, date_creation, employe_id) VALUES (%s, NOW(), %s)"
    valeurs = (os.path.basename(fichier), employe_id)
    
    try:
        cursor.execute(query, valeurs)
        conn.commit()
        print(f"✅ Fichier {fichier} enregistré dans la base de données.")
    except mysql.connector.Error as err:
        print(f"❌ Erreur MySQL : {err}")
    finally:
        cursor.close()
        conn.close()

# 🔹 Démarrer la surveillance de répertoire
def demarrer_surveillance():
    dossier_surveille = "/home/ftpuser/ftp"
    event_handler = SurveilleurFTP()
    observer = Observer()
    observer.schedule(event_handler, dossier_surveille, recursive=True)
    observer.start()
    print(f"🔍 Surveillance du répertoire : {dossier_surveille}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# 🔹 Routes de l'API Flask
@app.route('/')
def home():
    return render_template('smarttech.html')

@app.route('/api/<table>', methods=['GET'])
def lire_donnees(table):
    conn = connecter_db("smarttech")
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table}")
    resultats = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(resultats)

@app.route('/api/<table>/<int:id>', methods=['GET'])
def lire_une_donnee(table, id):
    conn = connecter_db("smarttech")
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (id,))
    resultat = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(resultat or {})

@app.route('/api/<table>', methods=['POST'])
def creer_donnee(table):
    conn = connecter_db("smarttech")
    cursor = conn.cursor()
    data = request.json
    
    colonnes = ', '.join(data.keys())
    valeurs = tuple(data.values())
    placeholders = ', '.join(['%s'] * len(valeurs))
    
    query = f"INSERT INTO {table} ({colonnes}) VALUES ({placeholders})"
    
    try:
        cursor.execute(query, valeurs)
        conn.commit()
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"error": str(err)}), 500
    finally:
        cursor.close()
        conn.close()

    # Si la table est "employe", créer un compte email
    if table == "employe" and "email" in data:
        creer_compte_email(data["email"], "motdepasse_par_defaut")  # Mot de passe par défaut

    return jsonify({"message": "Donnée ajoutée avec succès!"})

@app.route('/api/<table>/<int:id>', methods=['PUT'])
def mettre_a_jour_donnee(table, id):
    conn = connecter_db("smarttech")
    cursor = conn.cursor()
    data = request.json

    set_clause = ', '.join([f"{col} = %s" for col in data.keys()])
    valeurs = tuple(data.values()) + (id,)

    query = f"UPDATE {table} SET {set_clause} WHERE id = %s"

    try:
        cursor.execute(query, valeurs)
        conn.commit()
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"error": str(err)}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({"message": "Mise à jour réussie!"})

@app.route('/api/<table>/<int:id>', methods=['DELETE'])
def supprimer_donnee(table, id):
    conn = connecter_db("smarttech")
    cursor = conn.cursor()
    query = f"DELETE FROM {table} WHERE id = %s"

    try:
        cursor.execute(query, (id,))
        conn.commit()
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({"error": str(err)}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({"message": "Suppression réussie!"})

# 🔹 Démarrer l'application Flask
if __name__ == "__main__":
    # Démarrer la surveillance de répertoire dans un thread séparé
    surveillance_thread = threading.Thread(target=demarrer_surveillance)
    surveillance_thread.daemon = True
    surveillance_thread.start()

    # Démarrer l'application Flask
    app.run(host="0.0.0.0", port=5000, debug=True)
