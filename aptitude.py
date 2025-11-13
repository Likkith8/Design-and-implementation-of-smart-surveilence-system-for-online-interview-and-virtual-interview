from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, flash
import os
import random
from flask_mail import Mail, Message
import cv2
from utils.detection import start_proctoring
from utils.report import generate_report
from datetime import datetime
import base64
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from utils.combined_detection import detect_cheating
from PIL import Image
from utils.face_recognition import match_face
import numpy as np


app = Flask(__name__)
app.secret_key = os.urandom(24)

# Global list to store cheating instances
cheating_instances = []

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'interviewprocesspsv@gmail.com'  # Sender's email
app.config['MAIL_PASSWORD'] = 'icjreblsvyosngwq'  # Use an app password if 2FA is enabled
app.config['MAIL_DEFAULT_SENDER'] = 'interviewprocesspsv@gmail.com'

# Initialize Flask-Mail
mail = Mail(app)

# Global variable to store OTP
otp_store = {}

# Route: Registration, OTP Verification, and Face Capture Page (Single Page)
@app.route('/register', methods=['GET', 'POST'])
def register_and_capture():
    if request.method == 'POST':
        if 'otp' in request.form:
            # OTP verification part
            email = request.form['email']
            entered_otp = request.form['otp']
            if email in otp_store and otp_store[email] == entered_otp:
                flash('OTP verified successfully!', 'success')
                # Invalidate OTP after verification
                del otp_store[email]  # Remove OTP after successful verification
                return redirect(url_for('capture_face', email=email))
            else:
                flash('Invalid OTP. Please try again.', 'danger')

        elif 'name' in request.form:
            # Registration and OTP sending part
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']

            # Generate OTP
            otp = generate_otp()
            otp_store[email] = otp

            # Send OTP to the user's email
            try:
                msg = Message('Your OTP Code', recipients=[email])
                msg.body = f'Your OTP code is {otp}'
                mail.send(msg)
                flash('OTP sent to your email. Please verify.', 'success')
                return render_template('register.html', step='verify', email=email)

            except Exception as e:
                flash('Failed to send OTP. Please try again.', 'danger')
                print(f"Error sending email: {e}")

    return render_template('register.html', step='register')

@app.route('/capture_face', methods=['GET', 'POST'])
def capture_face():
    if request.method == 'POST':
        # Get the JSON data from the request body
        data = request.get_json()

        # Extract the necessary data from the JSON object
        email = data.get('email')  # Assuming 'email' is being sent in the JSON
        image_data = data.get('image')  # Base64 image data
        
        # Check if both email and image data are present
        if not email or not image_data:
            return jsonify({"success": False, "message": "Missing email or image data"}), 400

        # Decode Base64 image data
        try:
            image_data = image_data.split(',')[1]  # Remove the data URL prefix
            image_bytes = base64.b64decode(image_data)

            # Save the face image
            image = Image.open(BytesIO(image_bytes))
            image_path = f'static/faces/{email}.jpg'  # Using email as the filename
            image.save(image_path)
        except Exception as e:
            return jsonify({"success": False, "message": f"Error processing image: {str(e)}"}), 500

        # Save user details with new fields (name, email, password)
        name = data.get('name')
        password = data.get('password')
        
        if not name or not password:
            return jsonify({"success": False, "message": "Missing name or password"}), 400

        with open('static/faces/users.txt', 'a') as file:
            file.write(f'{email},{name},{password}\n')

        # Success response
        return jsonify({"success": True, "message": f"Face captured successfully for {name} ({email})!"})

    # Render the template for GET requests (if necessary)
    return render_template('login.html', step='login')

# Home page route
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    # Access the email and OTP from the JSON data sent in the request
    data = request.get_json()  # Use .get_json() to handle JSON requests
    email = data.get('email')  # Safely retrieve the email
    otp = data.get('otp')  # Safely retrieve the OTP

    if not email or not otp:
        return jsonify({"success": False, "message": "Email and OTP are required"}), 400

    if otp_store.get(email) == otp:
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "Invalid OTP"})

# OTP generation function
def generate_otp():
    return ''.join(random.choices('0123456789', k=6))  # Generates a 6-digit OTP


# OTP sending API
@app.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()

    email = data.get('email')
    name = data.get('name')

    if not email or not name:
        return jsonify({'success': False, 'message': 'Email and name are required'}), 400

    # Generate OTP
    otp = ''.join(random.choices('0123456789', k=6))
    otp_store[email] = otp

    try:
        msg = Message('Your OTP Code', recipients=[email])
        msg.body = f'Hi {name}, your OTP code is: {otp}'
        mail.send(msg)
        return jsonify({'success': True, 'message': 'OTP sent successfully'})
    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({'success': False, 'message': 'Failed to send OTP'}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        image_data = request.form['image']  

        # Decode the Base64 image data
        try:
            image_data = image_data.split(',')[1]  
            image_bytes = base64.b64decode(image_data)
            frame = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
        except Exception as e:
            return jsonify({"success": False, "error": "Error processing the image data."})

        # Check if user exists and validate email/password
        user_found = False
        with open('static/faces/users.txt', 'r') as file:
            users = file.readlines()
            for user in users:
                registered_email, registered_name, registered_password = user.strip().split(',')
                if registered_email.lower() == email.lower() and registered_password == password:
                    user_found = True
                    registered_face_image_path = f'static/faces/{registered_email}.jpg'
                    break

        if not user_found:
            return jsonify({"success": False, "error": "Invalid email or password."})

        # Match the face from the webcam photo with the stored face image
        if not match_face(registered_email, frame):
            return jsonify({"success": False, "error": "Face does not match the registered face."})

        # Successful login
        print(f"Login successful for email: {email}")
        session['user'] = email  # Store email in session

        return jsonify({"success": True})

    return render_template('login.html')



@app.route('/exam', methods=['GET', 'POST'])
def exam():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        answers = {
            'q1': request.form['q1'],
            'q2': request.form['q2'],
            'q3': request.form['q3']
        }

        email = session['user']
        student_name = ''
        with open('static/faces/users.txt', 'r') as file:
            for user in file.readlines():
                registered_email, registered_name,registered_password = user.strip().split(',')
                if email == registered_email:
                    student_name = registered_name
                    break
        print(f"Cheating instances: {cheating_instances}")
        # Generate report with cheating instances
        report_filename = f"static/reports/{email}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        generate_report(report_filename, student_name, email, answers, cheating_instances)

        # Clear cheating instances after generating the report
        cheating_instances.clear()

        return redirect(url_for('home'))

    return render_template('exam.html')


@app.route('/video_feed')
def video_feed():
    print("Video feed route accessed")
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


def gen_frames():
    global cheating_instances
    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()
        if not success:
            break
        print("Captured frame")
        # Detect cheating
        print("Calling detect_cheating function...")
        gaze_cheating, lip_cheating = detect_cheating(frame)
        print(f"Results - Gaze: {gaze_cheating}, Lip: {lip_cheating}")
        # Log cheating instances
        if gaze_cheating:
            cheating_instances.append({
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "type": "Gaze Movement"
            })	

        if lip_cheating:
            cheating_instances.append({
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "type": "Lip Movement"
            })

        # Encode and stream the frame
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    camera.release()

@app.route('/check_cheating')
def check_cheating():
    return jsonify({'cheating_detected': len(cheating_instances) > 0})


if __name__ == '__main__':
    if not os.path.exists('static/faces'):
        os.makedirs('static/faces')
    if not os.path.exists('static/temp'):
        os.makedirs('static/temp')
    if not os.path.exists('static/reports'):
        os.makedirs('static/reports')
    app.run(debug=True)
