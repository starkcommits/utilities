import frappe
import numpy as np
import base64
import io
import json
from PIL import Image
import cv2
import face_recognition

@frappe.whitelist()
def match_faces():
    """
    API endpoint to match faces between a selfie and ID card.
    
    Expected request format:
    {
        "selfie": "base64_encoded_image",
    }
    
    Returns:
    {
        "success": true/false,
        "match_score": float (0-1),
        "message": "Description of result"
    }
    """
    try:
        # Get the request data
        request_data = json.loads(frappe.request.data)
        
        # Validate request data
        if not request_data.get("selfie") or not request_data.get("id_card"):
            return {
                "success": False,
                "match_score": 0,
                "message": "Both selfie and ID card images are required"
            }
        
        # Decode images from base64
        selfie_image = decode_base64_image(request_data.get("selfie"))
        id_card_image = decode_base64_image(request_data.get("id_card"))
        
        # Convert PIL images to numpy arrays (RGB)
        selfie_array = np.array(selfie_image)
        id_card_array = np.array(id_card_image)
        
        # Convert RGB to BGR (face_recognition uses OpenCV which expects BGR)
        selfie_array = cv2.cvtColor(selfie_array, cv2.COLOR_RGB2BGR)
        id_card_array = cv2.cvtColor(id_card_array, cv2.COLOR_RGB2BGR)
        
        # Get match score
        match_result = compare_faces(selfie_array, id_card_array)
        
        return match_result
        
    except Exception as e:
        frappe.log_error(f"Face matching error: {str(e)}", "Face Matching API Error")
        return {
            "success": False,
            "match_score": 0,
            "message": f"Error processing images: {str(e)}"
        }

def decode_base64_image(base64_string):
    """Decode base64 string to PIL Image"""
    # Remove header if present
    if "base64," in base64_string:
        base64_string = base64_string.split("base64,")[1]
    
    # Decode base64 to bytes
    image_bytes = base64.b64decode(base64_string)
    
    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(image_bytes))
    
    return image

def compare_faces(selfie_image, id_card_image):
    """
    Compare faces in the selfie and ID card images.
    
    Args:
        selfie_image: Numpy array (BGR format) of selfie image
        id_card_image: Numpy array (BGR format) of ID card image
        
    Returns:
        Dictionary with match results
    """
    # Find face locations in both images
    selfie_face_locations = face_recognition.face_locations(selfie_image)
    id_card_face_locations = face_recognition.face_locations(id_card_image)
    
    # Check if faces were detected
    if not selfie_face_locations:
        return {
            "success": False,
            "match_score": 0,
            "message": "No face detected in selfie"
        }
    
    if not id_card_face_locations:
        return {
            "success": False,
            "match_score": 0,
            "message": "No face detected in ID card"
        }
    
    # Get face encodings (using the first face found in each image)
    selfie_encoding = face_recognition.face_encodings(selfie_image, [selfie_face_locations[0]])[0]
    id_card_encoding = face_recognition.face_encodings(id_card_image, [id_card_face_locations[0]])[0]
    
    # Calculate face distance (lower means more similar)
    face_distance = face_recognition.face_distance([selfie_encoding], id_card_encoding)[0]
    
    # Convert distance to similarity score (0-1, where 1 is perfect match)
    match_score = 1.0 - min(face_distance, 1.0)
    
    # Determine result message based on match score
    if match_score >= 0.6:
        message = "Face match successful"
        success = True
    else:
        message = "Face match unsuccessful"
        success = False
    
    # Return result
    return {
        "success": success,
        "match_score": round(float(match_score), 4),
        "message": message
    }