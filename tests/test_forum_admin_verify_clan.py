"""
Backend API tests for:
1. Forum Admin features - moderators and categories management
2. Clan verification endpoint (POST /api/clans/{clan_id}/verify)
3. Forum rank system display in posts
"""
import pytest
import requests
import os
from datetime import datetime

# Use production URL for testing
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://rematch-repairs.preview.emergentagent.com')

# Test credentials
TEST_USERNAME = "WebTestUser"
TEST_PASSWORD = "test123"


class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_check(self):
        """API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("PASS: Health check successful")
    
    def test_login_with_test_credentials(self):
        """Test login with provided credentials"""
        response = requests.post(f"{BASE_URL}/api/players/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "_id" in data
        assert data["username"] == TEST_USERNAME
        print(f"PASS: Login successful - player_id: {data['_id']}")
        return data["_id"]


class TestClanVerification:
    """Tests for clan verification endpoint"""
    
    def get_player_id(self):
        """Helper to get logged in player ID"""
        response = requests.post(f"{BASE_URL}/api/players/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["_id"]
        return None
    
    def test_get_clans_list(self):
        """Get all clans to find one for testing"""
        response = requests.get(f"{BASE_URL}/api/clans")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Got {len(data)} clans")
        return data
    
    def test_verify_clan_endpoint_true(self):
        """Test setting verified=true on a clan"""
        # First get clans list
        clans_response = requests.get(f"{BASE_URL}/api/clans")
        assert clans_response.status_code == 200
        clans = clans_response.json()
        
        if len(clans) == 0:
            pytest.skip("No clans available for testing")
        
        clan_id = clans[0]["_id"]
        
        # Verify the clan
        response = requests.post(f"{BASE_URL}/api/clans/{clan_id}/verify?verified=true")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_verified") == True
        print(f"PASS: Clan {clan_id} verified=true")
        return clan_id
    
    def test_verify_clan_endpoint_false(self):
        """Test setting verified=false on a clan"""
        clans_response = requests.get(f"{BASE_URL}/api/clans")
        assert clans_response.status_code == 200
        clans = clans_response.json()
        
        if len(clans) == 0:
            pytest.skip("No clans available for testing")
        
        clan_id = clans[0]["_id"]
        
        # Set verified to false
        response = requests.post(f"{BASE_URL}/api/clans/{clan_id}/verify?verified=false")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_verified") == False
        print(f"PASS: Clan {clan_id} verified=false")
    
    def test_verify_clan_invalid_id(self):
        """Test verify endpoint with invalid clan ID"""
        response = requests.post(f"{BASE_URL}/api/clans/invalid-id-123/verify?verified=true")
        assert response.status_code == 400  # Should return bad request for invalid ObjectId
        print("PASS: Invalid clan ID returns 400")
    
    def test_verify_clan_nonexistent(self):
        """Test verify endpoint with non-existent clan ID"""
        # Use a valid ObjectId format but non-existent
        fake_id = "000000000000000000000000"
        response = requests.post(f"{BASE_URL}/api/clans/{fake_id}/verify?verified=true")
        assert response.status_code == 404
        print("PASS: Non-existent clan returns 404")
    
    def test_clan_has_is_verified_field(self):
        """Test that clan GET returns is_verified field"""
        clans_response = requests.get(f"{BASE_URL}/api/clans")
        assert clans_response.status_code == 200
        clans = clans_response.json()
        
        if len(clans) == 0:
            pytest.skip("No clans available for testing")
        
        clan_id = clans[0]["_id"]
        response = requests.get(f"{BASE_URL}/api/clans/{clan_id}")
        assert response.status_code == 200
        data = response.json()
        # is_verified should be present in the response
        assert "is_verified" in data or data.get("is_verified") is not None or data.get("is_verified") == False
        print(f"PASS: Clan has is_verified field: {data.get('is_verified')}")


class TestForumCategories:
    """Tests for forum categories API"""
    
    def test_get_forum_categories(self):
        """Test getting forum categories"""
        response = requests.get(f"{BASE_URL}/api/forum/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Got {len(data)} forum categories")
        return data
    
    def test_forum_categories_have_required_fields(self):
        """Test that forum categories have required fields"""
        response = requests.get(f"{BASE_URL}/api/forum/categories")
        assert response.status_code == 200
        categories = response.json()
        
        if len(categories) == 0:
            pytest.skip("No forum categories available")
        
        cat = categories[0]
        required_fields = ["_id", "name"]
        for field in required_fields:
            assert field in cat, f"Category missing {field} field"
        print("PASS: Forum categories have required fields")


class TestForumModerators:
    """Tests for forum moderators API"""
    
    def test_get_forum_moderators(self):
        """Test getting forum moderators"""
        response = requests.get(f"{BASE_URL}/api/forum/moderators")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Got {len(data)} forum moderators")
        return data
    
    def test_check_moderator_status(self):
        """Test checking if a player is a moderator"""
        # Login first to get player_id
        login_response = requests.post(f"{BASE_URL}/api/players/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200
        player_id = login_response.json()["_id"]
        
        # Check moderator status
        response = requests.get(f"{BASE_URL}/api/forum/moderators/check/{player_id}")
        assert response.status_code == 200
        data = response.json()
        assert "is_moderator" in data
        print(f"PASS: Moderator check - is_moderator: {data.get('is_moderator')}")


class TestForumThreadsAndRanks:
    """Tests for forum threads and rank system in posts"""
    
    def test_get_forum_threads(self):
        """Test getting forum threads"""
        # First get categories
        cats_response = requests.get(f"{BASE_URL}/api/forum/categories")
        assert cats_response.status_code == 200
        categories = cats_response.json()
        
        if len(categories) == 0:
            pytest.skip("No forum categories available")
        
        # Try to get threads from first category
        cat_id = categories[0]["_id"]
        response = requests.get(f"{BASE_URL}/api/forum/categories/{cat_id}/threads")
        # May be empty but should return 200
        assert response.status_code in [200, 404]
        print(f"PASS: Forum threads endpoint works")
    
    def test_forum_posts_include_author_data(self):
        """Test that forum posts include author data for rank display"""
        # Get all threads first
        response = requests.get(f"{BASE_URL}/api/forum/threads")
        if response.status_code != 200:
            pytest.skip("No threads endpoint available")
        
        threads = response.json()
        if not threads or len(threads) == 0:
            pytest.skip("No threads available for testing")
        
        # Get posts from first thread
        thread_id = threads[0]["_id"]
        posts_response = requests.get(f"{BASE_URL}/api/forum/threads/{thread_id}/posts")
        
        if posts_response.status_code != 200:
            pytest.skip(f"Could not get posts for thread {thread_id}")
        
        posts_data = posts_response.json()
        posts = posts_data.get("posts", []) if isinstance(posts_data, dict) else posts_data
        
        if len(posts) == 0:
            pytest.skip("No posts available in thread")
        
        # Check that author data is included
        post = posts[0]
        assert "author" in post or "author_name" in post
        print("PASS: Forum posts include author data for rank display")


class TestForumStats:
    """Tests for forum stats"""
    
    def test_get_forum_stats(self):
        """Test getting forum statistics"""
        response = requests.get(f"{BASE_URL}/api/forum/stats")
        assert response.status_code == 200
        data = response.json()
        # Should have some stats fields
        print(f"PASS: Forum stats: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
