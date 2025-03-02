@app.route('/register', methods=['POST'])
def register():
    try:
        # Debugging print statements
        print("Incoming Request Data:", request.form)

        # Fetch input data
        username = request.form.get('username')
        mobile_no = request.form.get('mobile_no')
        password = request.form.get('password')
        profile_pic = request.files.get('profile_pic')  # Optional field

        # Check for missing fields
        if not username or not mobile_no or not password:
            return jsonify({"error": "Missing required fields"}), 400

        # Hash password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Handle profile picture if provided
        profile_pic_path = None
        if profile_pic:
            profile_pic_path = f"uploads/{profile_pic.filename}"
            profile_pic.save(profile_pic_path)

        # Create new user
        new_user = User(username=username, mobile_no=mobile_no, password=hashed_password, profile_pic=profile_pic_path)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({"message": "User registered successfully!"}), 201

    except Exception as e:
        print("Error:", str(e))  # Print error in terminal
        return jsonify({"error": str(e)}), 500