from flask import Flask, render_template, request, jsonify
import sqlite3
import requests

app = Flask(__name__)

MAILGUN_API_BASE_URL = "https://api.mailgun.net/v3"

# Initialize SQLite database and handle schema changes
def init_db():
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()

    # Check if the 'domains' table exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE,
            api_key TEXT,
            is_primary BOOLEAN DEFAULT TRUE,
            primary_domain_id INTEGER
        );
    ''')
    
    # Check if 'is_primary' column exists, if not, add it
    c.execute("PRAGMA table_info(domains)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'is_primary' not in columns:
        c.execute("ALTER TABLE domains ADD COLUMN is_primary BOOLEAN DEFAULT TRUE")

    if 'primary_domain_id' not in columns:
        c.execute("ALTER TABLE domains ADD COLUMN primary_domain_id INTEGER")

    conn.commit()
    conn.close()


# Home route
@app.route('/')
def home():
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT domain FROM domains')
    domains = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('index.html', domains=domains)


@app.route('/add-domain', methods=['POST'])
def add_domain():
    domain = request.form['domain']
    api_key = request.form['api_key']
    is_primary = request.form.get('is_primary', 'false') == 'true'
    primary_domain_id = request.form.get('primary_domain_id') if not is_primary else None

    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO domains (domain, api_key, is_primary, primary_domain_id) VALUES (?, ?, ?, ?)', 
              (domain, api_key, is_primary, primary_domain_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route('/get-domain-details', methods=['GET'])
def get_domain_details():
    domain = request.args.get('domain')
    
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT id, domain, api_key, is_primary, primary_domain_id FROM domains WHERE domain = ?', (domain,))
    result = c.fetchone()
    conn.close()

    if result:
        id, domain, api_key, is_primary, primary_domain_id = result
        return jsonify({
            "id": id,
            "domain": domain,
            "api_key": api_key,
            "is_primary": is_primary,
            "primary_domain_id": primary_domain_id
        })
    else:
        return jsonify({"error": "Domain not found"}), 404


# Fetch API key for a domain
@app.route('/get-api-key', methods=['GET'])
def get_api_key():
    domain = request.args.get('domain')
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key FROM domains WHERE domain = ?', (domain,))
    api_key = c.fetchone()
    conn.close()

    if api_key:
        return jsonify({"api_key": api_key[0]})
    else:
        return jsonify({"error": "No API key found"}), 404

# Update domain API key
@app.route('/update-domain/<domain>', methods=['POST'])
def update_domain(domain):
    new_api_key = request.form.get('api_key')

    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('UPDATE domains SET api_key = ? WHERE domain = ?', (new_api_key, domain))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Domain updated successfully'})

# Delete domain
@app.route('/delete-domain/<domain>', methods=['DELETE'])
def delete_domain(domain):
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('DELETE FROM domains WHERE domain = ?', (domain,))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

# Fetch templates from Mailgun
@app.route('/get-templates', methods=['GET'])
def get_templates():
    domain = request.args.get('domain')
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key FROM domains WHERE domain = ?', (domain,))
    api_key = c.fetchone()
    conn.close()

    if not api_key:
        return jsonify({"error": "No API key found for the domain"}), 404

    # Use the API key to fetch templates from Mailgun
    try:
        response = requests.get(
            f"{MAILGUN_API_BASE_URL}/{domain}/templates",
            auth=("api", api_key[0])
        )
        if response.status_code == 200:
            templates = response.json().get('items', [])
            return jsonify(templates)
        else:
            return jsonify({"error": "Unable to fetch templates"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-mail-lists', methods=['GET'])
def get_mail_lists():
    domain_id = request.args.get('domain_id')
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key FROM domains WHERE id = ?', (domain_id,))
    api_key = c.fetchone()
    conn.close()

    if not api_key:
        return jsonify({"error": "No API key found for the domain"}), 404

    # Use the API key to fetch mail lists from Mailgun
    try:
        response = requests.get(
            f"{MAILGUN_API_BASE_URL}/lists",
            auth=("api", api_key[0])
        )
        if response.status_code == 200:
            mail_lists = response.json().get('items', [])
            return jsonify(mail_lists)
        else:
            return jsonify({"error": "Unable to fetch mail lists"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/get-mail-list-details', methods=['GET'])
def get_mail_list_details():
    mail_list = request.args.get('mail_list')
    domain = request.args.get('domain')
    
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key, primary_domain_id, is_primary FROM domains WHERE domain = ?', (domain,))
    api_key, primary_domain_id, is_primary = c.fetchone()
    # if the domain is not primary, get the primary domain's API key
    if not is_primary:
        c.execute('SELECT api_key FROM domains WHERE id = ?', (primary_domain_id,))
        api_key = c.fetchone()
    conn.close()

    if not api_key:
        return jsonify({"error": "No API key found for the domain"}), 404

    # Fetch mail list details (number of recipients) from Mailgun
    try:
        response = requests.get(
            f"{MAILGUN_API_BASE_URL}/lists/{mail_list}/members",
            auth=("api", api_key[0]),
            params={"limit": 1}  # Fetch just enough to get the count
        )
        if response.status_code == 200:
            members_count = response.json().get('total_count', 0)
            return jsonify({'mail_list': mail_list, 'recipients': members_count})
        else:
            return jsonify({'error': 'Failed to fetch mail list details', 'details': response.text}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/send-test-email', methods=['POST'])
def send_test_email():
    domain = request.form.get('domain')
    template = request.form.get('template')
    from_address = request.form.get('from_address')
    reply_to = request.form.get('reply_to', None)  # Optional reply-to address
    test_emails = [email.strip() for email in request.form.get('test_emails', '').split(',')]
    subject = request.form.get('subject', None)
    
    if not domain or not template or not test_emails or not from_address:
        return jsonify({'error': 'Missing required fields'}), 400

    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key FROM domains WHERE domain = ?', (domain,))
    api_key = c.fetchone()
    conn.close()

    if not api_key:
        return jsonify({"error": "No API key found for the domain"}), 404

    # Prepare the data for sending email via Mailgun API
    data = {
        "from": from_address,
        "to": test_emails,
        "subject": subject,
        "template": template,
    }

    if reply_to:
        data["h:Reply-To"] = reply_to  # Include Reply-To header if provided

    # Send the email via Mailgun API
    try:
        response = requests.post(
            f"{MAILGUN_API_BASE_URL}/{domain}/messages",
            auth=("api", api_key[0]),
            data=data
        )
        if response.status_code == 200:
            return jsonify({'status': 'success', 'message': 'Test email sent successfully!'})
        else:
            return jsonify({'error': 'Failed to send email', 'details': response.text}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/send-live-email', methods=['POST'])
def send_live_email():
    domain = request.form.get('domain')
    template = request.form.get('template')
    mail_list = request.form.get('mail_list')
    from_address = request.form.get('from_address')
    reply_to = request.form.get('reply_to', None)  # Optional reply-to address
    include_test_list = request.form.get('include_test_list') == 'true'
    test_emails = [email.strip() for email in request.form.get('test_emails', '').split(',')] if include_test_list else []  # Trim whitespace
    subject = request.form.get('subject', None)

    if not domain or not template or not mail_list or not from_address:
        return jsonify({'error': 'Missing required fields'}), 400

    # Fetch the API key for the domain
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT api_key FROM domains WHERE domain = ?', (domain,))
    api_key = c.fetchone()
    conn.close()

    if not api_key:
        return jsonify({"error": "No API key found for the domain"}), 404

    # Prepare the recipient list
    recipient_list = [mail_list]
    if include_test_list and test_emails:
        recipient_list.extend(test_emails)

    # Prepare the data for sending the live email via Mailgun API
    data = {
        "from": from_address,
        "to": recipient_list,  # This will send the email to the mailing list and test emails
        "subject": subject,
        "template": template,
    }

    if reply_to:
        data["h:Reply-To"] = reply_to  # Include Reply-To header if provided

    # Send the email via Mailgun API
    try:
        response = requests.post(
            f"{MAILGUN_API_BASE_URL}/{domain}/messages",
            auth=("api", api_key[0]),
            data=data
        )
        if response.status_code == 200:
            return jsonify({'status': 'success', 'message': 'Live email sent successfully!'})
        else:
            return jsonify({'error': 'Failed to send live email', 'details': response.text}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-domains', methods=['GET'])
def get_domains():
    conn = sqlite3.connect('domains.db')
    c = conn.cursor()
    c.execute('SELECT id, domain AS name, api_key, is_primary FROM domains')
    domains = [{'id': row[0], 'name': row[1], 'api_key': row[2], 'is_primary': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({'domains': domains})

init_db()

if __name__ == '__main__':
    app.run(debug=True)
