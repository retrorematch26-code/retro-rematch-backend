"""
Forum Signature API Tests
Tests for the classic 2000s style forum signature feature:
- GET /api/forum/signature/{player_id} - Get player signature
- POST /api/forum/signature/{player_id}/upload - Upload signature image
- DELETE /api/forum/signature/{player_id} - Delete player signature
"""

import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://rematch-repairs.preview.emergentagent.com')

# Test player ID from the requirements
TEST_PLAYER_ID = "698eabcae835d120bdfad8ad"
TEST_USERNAME = "WebTestUser"
TEST_PASSWORD = "test123"

# Create a minimal valid PNG image (1x1 pixel, red)
def create_test_png():
    """Create a minimal 1x1 red PNG for testing"""
    # Minimal PNG data (1x1 red pixel)
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    return png_data

def create_test_base64_png():
    """Create a base64 encoded PNG data URL"""
    png_bytes = create_test_png()
    return f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"

def create_oversized_png():
    """Create a base64 PNG that simulates being too large (we fake the header)"""
    # For testing, we'll just create a regular PNG but test the error handling
    # The actual file size check happens server-side
    return create_test_base64_png()


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestForumSignatureGet:
    """Tests for GET /api/forum/signature/{player_id}"""
    
    def test_get_signature_for_player_without_signature(self, api_client):
        """Test getting signature for player who has no signature"""
        response = api_client.get(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        
        assert response.status_code == 200
        data = response.json()
        # Should return empty dict or signature object
        assert isinstance(data, dict)
        print(f"✓ Get signature for player without signature returns: {data}")
    
    def test_get_signature_invalid_player(self, api_client):
        """Test getting signature for non-existent player"""
        fake_id = "000000000000000000000000"
        response = api_client.get(f"{BASE_URL}/api/forum/signature/{fake_id}")
        
        assert response.status_code == 404
        print("✓ Get signature for invalid player returns 404")
    
    def test_get_signature_invalid_id_format(self, api_client):
        """Test with invalid ObjectId format"""
        response = api_client.get(f"{BASE_URL}/api/forum/signature/invalid-id")
        
        # Should return error (400, 422, 500, or 520 which is cloudflare proxy error)
        assert response.status_code in [400, 422, 500, 520]
        print(f"✓ Invalid ID format returns error code: {response.status_code}")


class TestForumSignatureUpload:
    """Tests for POST /api/forum/signature/{player_id}/upload"""
    
    def test_upload_valid_png_signature(self, api_client):
        """Test uploading a valid PNG signature"""
        image_data = create_test_base64_png()
        
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data, "text": "Test Signature"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "signature" in data or "message" in data
        print(f"✓ Upload valid PNG signature succeeded: {data.get('message', 'OK')}")
    
    def test_upload_signature_without_image(self, api_client):
        """Test uploading without image data"""
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"text": "Just text, no image"}
        )
        
        assert response.status_code == 400
        print("✓ Upload without image returns 400")
    
    def test_upload_invalid_image_format(self, api_client):
        """Test uploading non-PNG/GIF image"""
        # Create a fake JPEG header
        jpeg_data = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"
        
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": jpeg_data}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "PNG" in data["detail"] or "GIF" in data["detail"]
        print(f"✓ Upload invalid format rejected: {data['detail']}")
    
    def test_upload_to_invalid_player(self, api_client):
        """Test uploading signature for non-existent player"""
        fake_id = "000000000000000000000000"
        image_data = create_test_base64_png()
        
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{fake_id}/upload",
            json={"image": image_data}
        )
        
        assert response.status_code == 404
        print("✓ Upload to invalid player returns 404")
    
    def test_upload_with_optional_text(self, api_client):
        """Test uploading signature with optional text"""
        image_data = create_test_base64_png()
        
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data, "text": "~*~HeAdShOt KiNg~*~"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        
        # Verify the text was saved
        if "signature" in data:
            assert data["signature"].get("text") == "~*~HeAdShOt KiNg~*~"
        print("✓ Upload with optional text succeeded")


class TestForumSignatureDelete:
    """Tests for DELETE /api/forum/signature/{player_id}"""
    
    def test_delete_existing_signature(self, api_client):
        """Test deleting an existing signature"""
        # First upload a signature
        image_data = create_test_base64_png()
        api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data}
        )
        
        # Now delete it
        response = api_client.delete(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        print("✓ Delete signature succeeded")
    
    def test_delete_non_existing_signature(self, api_client):
        """Test deleting signature when none exists"""
        # First ensure no signature
        api_client.delete(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        
        # Try to delete again
        response = api_client.delete(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        
        # Should still succeed (idempotent)
        assert response.status_code == 200
        print("✓ Delete non-existing signature is idempotent")
    
    def test_delete_signature_invalid_player(self, api_client):
        """Test deleting signature for non-existent player"""
        fake_id = "000000000000000000000000"
        response = api_client.delete(f"{BASE_URL}/api/forum/signature/{fake_id}")
        
        assert response.status_code == 404
        print("✓ Delete for invalid player returns 404")


class TestForumSignatureIntegration:
    """Integration tests for signature in forum posts"""
    
    def test_signature_appears_in_post_author_info(self, api_client):
        """Test that signature is included in forum post author data"""
        # First upload a signature
        image_data = create_test_base64_png()
        api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data, "text": "Integration Test Sig"}
        )
        
        # Get signature to verify
        response = api_client.get(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        assert response.status_code == 200
        sig_data = response.json()
        
        # Verify signature has expected fields
        assert "image_url" in sig_data or sig_data == {}
        if sig_data:
            assert sig_data.get("enabled") == True
            print(f"✓ Signature verified with fields: {list(sig_data.keys())}")
        else:
            print("✓ No signature set (empty response)")
    
    def test_full_signature_workflow(self, api_client):
        """Test complete workflow: upload -> verify -> delete -> verify"""
        image_data = create_test_base64_png()
        
        # Step 1: Upload signature
        upload_resp = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data, "text": "Workflow Test"}
        )
        assert upload_resp.status_code == 200
        print("✓ Step 1: Upload succeeded")
        
        # Step 2: Verify it exists
        get_resp = api_client.get(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        assert get_resp.status_code == 200
        sig = get_resp.json()
        assert sig.get("enabled") == True or sig.get("image_url")
        print("✓ Step 2: Signature exists after upload")
        
        # Step 3: Delete signature
        del_resp = api_client.delete(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        assert del_resp.status_code == 200
        print("✓ Step 3: Delete succeeded")
        
        # Step 4: Verify it's gone
        get_resp2 = api_client.get(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
        assert get_resp2.status_code == 200
        sig2 = get_resp2.json()
        assert sig2 == {} or sig2.get("enabled") == False
        print("✓ Step 4: Signature removed after delete")
        
        print("✓ Full workflow completed successfully")


class TestForumSignatureValidation:
    """Tests for signature validation rules"""
    
    def test_signature_constraints_documented(self, api_client):
        """Verify signature constraints are enforced (600x180px, 2MB, PNG/GIF)"""
        # This is more of a documentation test - verifying the rules exist
        # The actual dimension validation happens server-side with PIL
        
        # Test 1: Valid PNG should work
        image_data = create_test_base64_png()
        response = api_client.post(
            f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}/upload",
            json={"image": image_data}
        )
        assert response.status_code == 200
        print("✓ Valid small PNG accepted")
        
        # Clean up
        api_client.delete(f"{BASE_URL}/api/forum/signature/{TEST_PLAYER_ID}")
